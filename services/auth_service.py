from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import SECRET_KEY
from database.models import AppSession, Client, Device, EmailLoginCode, LoginCode

ACCESS_TOKEN_TTL_MINUTES = 30
REFRESH_TOKEN_TTL_DAYS = 30
LOGIN_CODE_TTL_MINUTES = 5
EMAIL_LOGIN_CODE_TTL_MINUTES = 10
EMAIL_LOGIN_CODE_COOLDOWN_SECONDS = 60
JWT_ALGORITHM = "HS256"


@dataclass
class AuthTokens:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


@dataclass
class LoginResult:
    client: Client
    device: Device
    tokens: AuthTokens


@dataclass
class RequestEmailCodeResult:
    email: str
    code: str
    expires_at: datetime
    cooldown_seconds: int


class AuthError(Exception):
    pass


class InvalidLoginCodeError(AuthError):
    pass


class ExpiredLoginCodeError(AuthError):
    pass


class InvalidRefreshTokenError(AuthError):
    pass


class RevokedSessionError(AuthError):
    pass


class AuthService:
    @staticmethod
    def _utcnow() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _generate_code(length: int = 8) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def _generate_email_code() -> str:
        return f"{secrets.randbelow(1000000):06d}"

    @staticmethod
    def _generate_token() -> str:
        return secrets.token_urlsafe(48)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _build_email_identity(email: str) -> tuple[str, str]:
        digest = hashlib.sha256(email.encode("utf-8")).hexdigest()
        telegram_id = f"email:{digest[:24]}"
        login = f"email_{digest[:12]}"
        return telegram_id, login

    @staticmethod
    def _build_access_token(client: Client, device: Device) -> tuple[str, int]:
        now = AuthService._utcnow()
        expires_at = now + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES)

        payload = {
            "sub": str(client.id),
            "public_id": client.public_id,
            "telegram_id": client.telegram_id,
            "device_id": device.id,
            "platform": device.platform,
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)
        expires_in = ACCESS_TOKEN_TTL_MINUTES * 60
        return token, expires_in

    @staticmethod
    def _decode_access_token(access_token: str) -> dict:
        try:
            payload = jwt.decode(access_token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        except jwt.PyJWTError as exc:
            raise InvalidRefreshTokenError("Invalid token") from exc

        if payload.get("type") != "access":
            raise InvalidRefreshTokenError("Invalid token type")

        return payload

    @staticmethod
    async def create_login_code(
        db: AsyncSession,
        telegram_id: str,
        platform: Optional[str] = None,
        device_uid: Optional[str] = None,
    ) -> LoginCode:
        result = await db.execute(
            select(Client).where(Client.telegram_id == str(telegram_id))
        )
        client = result.scalar_one_or_none()
        if not client:
            raise AuthError("Client not found")

        now = AuthService._utcnow()

        await db.execute(
            update(LoginCode)
            .where(
                LoginCode.client_id == client.id,
                LoginCode.used_at.is_(None),
                LoginCode.expires_at < now,
            )
            .values(used_at=now)
        )

        code = AuthService._generate_code()
        login_code = LoginCode(
            client_id=client.id,
            code=code,
            platform=platform or "any",
            device_uid=device_uid,
            expires_at=now + timedelta(minutes=LOGIN_CODE_TTL_MINUTES),
        )
        db.add(login_code)
        await db.commit()
        await db.refresh(login_code)
        return login_code

    @staticmethod
    async def request_email_code(
        db: AsyncSession,
        email: str,
    ) -> RequestEmailCodeResult:
        normalized = AuthService._normalize_email(email)
        now = AuthService._utcnow()

        recent_result = await db.execute(
            select(EmailLoginCode)
            .where(
                EmailLoginCode.email == normalized,
                EmailLoginCode.created_at >= now - timedelta(seconds=EMAIL_LOGIN_CODE_COOLDOWN_SECONDS),
            )
            .order_by(EmailLoginCode.id.desc())
        )
        recent = recent_result.scalar_one_or_none()
        if recent:
            raise AuthError("Код уже отправлен. Попробуйте чуть позже.")

        client_result = await db.execute(
            select(Client).where(Client.email == normalized)
        )
        client = client_result.scalar_one_or_none()

        code = AuthService._generate_email_code()
        row = EmailLoginCode(
            client_id=client.id if client else None,
            email=normalized,
            code_hash=AuthService._hash_token(code),
            expires_at=now + timedelta(minutes=EMAIL_LOGIN_CODE_TTL_MINUTES),
            attempts=0,
        )
        db.add(row)
        await db.commit()

        return RequestEmailCodeResult(
            email=normalized,
            code=code,
            expires_at=row.expires_at,
            cooldown_seconds=EMAIL_LOGIN_CODE_COOLDOWN_SECONDS,
        )

    @staticmethod
    async def send_email_login_code(email: str, code: str) -> None:
        # Временная заглушка. Здесь подключишь SMTP / Brevo / Mailgun / SendGrid.
        print(f"[email-auth] send code {code} to {email}")

    @staticmethod
    async def _get_or_create_client_by_email(
        db: AsyncSession,
        email: str,
    ) -> Client:
        normalized = AuthService._normalize_email(email)

        result = await db.execute(
            select(Client).where(Client.email == normalized)
        )
        client = result.scalar_one_or_none()
        if client:
            return client

        synthetic_telegram_id, synthetic_login = AuthService._build_email_identity(normalized)

        client = Client(
            telegram_id=synthetic_telegram_id,
            full_name=normalized.split("@")[0],
            login=synthetic_login,
            email=normalized,
            status="active",
            created_via="email",
            default_language="ru",
            is_active=True,
            is_paid=False,
        )
        db.add(client)
        await db.commit()
        await db.refresh(client)
        return client

    @staticmethod
    async def login_by_email_code(
        db: AsyncSession,
        email: str,
        code: str,
        device_uid: str,
        platform: str,
        device_name: Optional[str] = None,
        app_version: Optional[str] = None,
        os_version: Optional[str] = None,
    ) -> LoginResult:
        normalized = AuthService._normalize_email(email)
        now = AuthService._utcnow()

        result = await db.execute(
            select(EmailLoginCode)
            .where(
                EmailLoginCode.email == normalized,
                EmailLoginCode.consumed_at.is_(None),
            )
            .order_by(EmailLoginCode.id.desc())
        )
        login_row = result.scalar_one_or_none()

        if not login_row:
            raise InvalidLoginCodeError("Login code not found")

        if login_row.expires_at < now:
            raise ExpiredLoginCodeError("Login code expired")

        expected_hash = AuthService._hash_token(code.strip())
        if login_row.code_hash != expected_hash:
            login_row.attempts += 1
            await db.commit()
            raise InvalidLoginCodeError("Invalid login code")

        client = await AuthService._get_or_create_client_by_email(
            db=db,
            email=normalized,
        )

        if client.status != "active":
            raise AuthError("Client is not active")

        if client.email != normalized:
            client.email = normalized

        device = await AuthService._get_or_create_device(
            db=db,
            client=client,
            device_uid=device_uid,
            platform=platform,
            device_name=device_name,
            app_version=app_version,
            os_version=os_version,
        )

        login_row.client_id = client.id
        login_row.consumed_at = now
        client.last_login_at = now

        await db.commit()

        tokens = await AuthService._create_session(
            db=db,
            client=client,
            device=device,
        )

        return LoginResult(
            client=client,
            device=device,
            tokens=tokens,
        )

    @staticmethod
    async def _get_or_create_device(
        db: AsyncSession,
        client: Client,
        device_uid: str,
        platform: str,
        device_name: Optional[str] = None,
        app_version: Optional[str] = None,
        os_version: Optional[str] = None,
    ) -> Device:
        result = await db.execute(
            select(Device).where(Device.device_uid == device_uid)
        )
        device = result.scalar_one_or_none()

        now = AuthService._utcnow()

        if device:
            if device.client_id != client.id:
                raise AuthError("Device already belongs to another user")

            device.platform = platform
            device.device_name = device_name
            device.app_version = app_version
            device.os_version = os_version
            device.is_active = True
            device.is_revoked = False
            device.last_seen_at = now

            await db.commit()
            await db.refresh(device)
            return device

        device = Device(
            client_id=client.id,
            device_uid=device_uid,
            platform=platform,
            device_name=device_name,
            app_version=app_version,
            os_version=os_version,
            is_active=True,
            is_revoked=False,
            last_seen_at=now,
        )
        db.add(device)
        await db.commit()
        await db.refresh(device)
        return device

    @staticmethod
    async def _create_session(
        db: AsyncSession,
        client: Client,
        device: Device,
    ) -> AuthTokens:
        refresh_token = AuthService._generate_token()
        refresh_token_hash = AuthService._hash_token(refresh_token)

        now = AuthService._utcnow()
        expires_at = now + timedelta(days=REFRESH_TOKEN_TTL_DAYS)

        session = AppSession(
            client_id=client.id,
            device_id=device.id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            created_at=now,
            last_used_at=now,
        )
        db.add(session)

        client.last_login_at = now

        await db.commit()
        await db.refresh(session)

        access_token, expires_in = AuthService._build_access_token(client, device)

        return AuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
        )

    @staticmethod
    async def login_by_code(
        db: AsyncSession,
        code: str,
        device_uid: str,
        platform: str,
        device_name: Optional[str] = None,
        app_version: Optional[str] = None,
        os_version: Optional[str] = None,
    ) -> LoginResult:
        result = await db.execute(
            select(LoginCode).where(LoginCode.code == code)
        )
        login_code = result.scalar_one_or_none()

        if not login_code:
            raise InvalidLoginCodeError("Login code not found")

        now = AuthService._utcnow()

        if login_code.used_at is not None:
            raise InvalidLoginCodeError("Login code already used")

        if login_code.expires_at < now:
            raise ExpiredLoginCodeError("Login code expired")

        if login_code.platform and login_code.platform != "any":
            if login_code.platform != platform:
                raise InvalidLoginCodeError("Login code platform mismatch")

        if login_code.device_uid and login_code.device_uid != device_uid:
            raise InvalidLoginCodeError("Login code device mismatch")

        client_result = await db.execute(
            select(Client).where(Client.id == login_code.client_id)
        )
        client = client_result.scalar_one_or_none()
        if not client:
            raise AuthError("Client not found")

        if client.status != "active":
            raise AuthError("Client is not active")

        device = await AuthService._get_or_create_device(
            db=db,
            client=client,
            device_uid=device_uid,
            platform=platform,
            device_name=device_name,
            app_version=app_version,
            os_version=os_version,
        )

        login_code.used_at = now
        await db.commit()

        tokens = await AuthService._create_session(
            db=db,
            client=client,
            device=device,
        )

        return LoginResult(
            client=client,
            device=device,
            tokens=tokens,
        )

    @staticmethod
    async def refresh_tokens(
        db: AsyncSession,
        refresh_token: str,
    ) -> AuthTokens:
        refresh_token_hash = AuthService._hash_token(refresh_token)
        result = await db.execute(
            select(AppSession).where(AppSession.refresh_token_hash == refresh_token_hash)
        )
        session = result.scalar_one_or_none()

        if not session:
            raise InvalidRefreshTokenError("Session not found")

        now = AuthService._utcnow()

        if session.revoked_at is not None:
            raise RevokedSessionError("Session revoked")

        if session.expires_at < now:
            raise InvalidRefreshTokenError("Refresh token expired")

        client_result = await db.execute(
            select(Client).where(Client.id == session.client_id)
        )
        client = client_result.scalar_one_or_none()
        if not client:
            raise InvalidRefreshTokenError("Client not found")

        device_result = await db.execute(
            select(Device).where(Device.id == session.device_id)
        )
        device = device_result.scalar_one_or_none()
        if not device:
            raise InvalidRefreshTokenError("Device not found")

        if device.is_revoked or not device.is_active:
            raise RevokedSessionError("Device revoked")

        session.last_used_at = now
        device.last_seen_at = now
        client.last_login_at = now

        new_refresh_token = AuthService._generate_token()
        session.refresh_token_hash = AuthService._hash_token(new_refresh_token)
        session.expires_at = now + timedelta(days=REFRESH_TOKEN_TTL_DAYS)

        await db.commit()

        access_token, expires_in = AuthService._build_access_token(client, device)

        return AuthTokens(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=expires_in,
        )

    @staticmethod
    async def logout(
        db: AsyncSession,
        refresh_token: str,
    ) -> bool:
        refresh_token_hash = AuthService._hash_token(refresh_token)
        result = await db.execute(
            select(AppSession).where(AppSession.refresh_token_hash == refresh_token_hash)
        )
        session = result.scalar_one_or_none()
        if not session:
            return False

        if session.revoked_at is None:
            session.revoked_at = AuthService._utcnow()
            await db.commit()

        return True

    @staticmethod
    async def logout_all_for_client(
        db: AsyncSession,
        client_id: int,
    ) -> int:
        result = await db.execute(
            select(AppSession).where(
                AppSession.client_id == client_id,
                AppSession.revoked_at.is_(None),
            )
        )
        sessions = result.scalars().all()

        now = AuthService._utcnow()
        count = 0

        for session in sessions:
            session.revoked_at = now
            count += 1

        if count:
            await db.commit()

        return count

    @staticmethod
    async def get_client_by_access_token(
        db: AsyncSession,
        access_token: str,
    ) -> Optional[Client]:
        payload = AuthService._decode_access_token(access_token)
        client_id = payload.get("sub")
        if not client_id:
            return None

        result = await db.execute(
            select(Client).where(Client.id == int(client_id))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_device_by_access_token(
        db: AsyncSession,
        access_token: str,
    ) -> Optional[Device]:
        payload = AuthService._decode_access_token(access_token)
        device_id = payload.get("device_id")
        if not device_id:
            return None

        result = await db.execute(
            select(Device).where(Device.id == int(device_id))
        )
        return result.scalar_one_or_none()