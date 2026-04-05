from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import SECRET_KEY
from database.models import (
    AppSession,
    Client,
    ClientVpnAccess,
    Device,
    EmailBindingCode,
    EmailLoginCode,
    LoginCode,
    SubscriptionHistory,
    YooKassaPayment,
)
from services.email_sender import send_login_code_email

ACCESS_TOKEN_TTL_MINUTES = 30
REFRESH_TOKEN_TTL_DAYS = 30
LOGIN_CODE_TTL_MINUTES = 5
EMAIL_LOGIN_CODE_TTL_MINUTES = 10
EMAIL_LOGIN_CODE_COOLDOWN_SECONDS = 60
JWT_ALGORITHM = "HS256"

logger = logging.getLogger(__name__)


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


@dataclass
class ConfirmEmailBindingResult:
    client: Client
    merged: bool
    source_client_id: Optional[int] = None
    target_client_id: Optional[int] = None


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
    def _max_datetime(first: Optional[datetime], second: Optional[datetime]) -> Optional[datetime]:
        if first and second:
            return max(first, second)
        return first or second

    @staticmethod
    def _merge_status(target_status: Optional[str], source_status: Optional[str]) -> str:
        statuses = {value for value in [target_status, source_status] if value}
        if "blocked" in statuses:
            return "blocked"
        if "deleted" in statuses:
            return "deleted"
        return target_status or source_status or "active"

    @staticmethod
    def _parse_notes(notes: Optional[str]) -> tuple[dict[str, str], list[str]]:
        data: dict[str, str] = {}
        raw_lines: list[str] = []

        if not notes:
            return data, raw_lines

        for line in notes.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if "=" in stripped:
                key, value = stripped.split("=", 1)
                data[key.strip()] = value.strip()
            else:
                raw_lines.append(stripped)

        return data, raw_lines

    @staticmethod
    def _dump_notes(data: dict[str, str], raw_lines: list[str]) -> Optional[str]:
        lines: list[str] = []
        for key in sorted(data.keys()):
            lines.append(f"{key}={data[key]}")
        lines.extend(raw_lines)
        return "\n".join(lines) if lines else None

    @staticmethod
    def _merge_notes(target_notes: Optional[str], source_notes: Optional[str]) -> Optional[str]:
        target_data, target_raw = AuthService._parse_notes(target_notes)
        source_data, source_raw = AuthService._parse_notes(source_notes)

        merged = dict(source_data)
        merged.update(target_data)

        source_trial = source_data.get("trial_used") == "true"
        target_trial = target_data.get("trial_used") == "true"
        if source_trial or target_trial:
            merged["trial_used"] = "true"

        max_devices_values: list[int] = []
        for candidate in [source_data.get("max_devices"), target_data.get("max_devices")]:
            if candidate and candidate.isdigit():
                max_devices_values.append(int(candidate))
        if max_devices_values:
            merged["max_devices"] = str(max(max_devices_values))

        if target_data.get("plan_code"):
            merged["plan_code"] = target_data["plan_code"]
        elif source_data.get("plan_code"):
            merged["plan_code"] = source_data["plan_code"]

        raw_lines: list[str] = []
        seen = set()
        for line in source_raw + target_raw:
            if line not in seen:
                seen.add(line)
                raw_lines.append(line)

        return AuthService._dump_notes(merged, raw_lines)

    @staticmethod
    async def _sync_legacy_access_fields(
        db: AsyncSession,
        client: Client,
        *,
        preserve_existing_if_no_pairs: bool = True,
    ) -> None:
        result = await db.execute(
            select(ClientVpnAccess)
            .where(
                ClientVpnAccess.client_id == client.id,
                ClientVpnAccess.is_enabled.is_(True),
            )
            .order_by(ClientVpnAccess.node_id.asc(), ClientVpnAccess.id.asc())
        )
        pairs = list(result.scalars().all())

        if not pairs:
            if not preserve_existing_if_no_pairs:
                client.login = None
                client.xui_uuid = None
                client.xui_email = None
                client.subscription_link = None
            client.updated_at = AuthService._utcnow()
            return

        primary = pairs[0]
        client.login = primary.xui_email or client.login
        client.xui_uuid = primary.xui_uuid
        client.xui_email = primary.xui_email
        client.subscription_link = primary.subscription_link
        client.updated_at = AuthService._utcnow()

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
            .limit(1)
        )
        recent = recent_result.scalars().first()
        if recent:
            raise AuthError("Код уже отправлен. Попробуйте чуть позже.")

        client_result = await db.execute(
            select(Client).where(Client.email == normalized)
        )
        client = client_result.scalar_one_or_none()

        await db.execute(
            update(EmailLoginCode)
            .where(
                EmailLoginCode.email == normalized,
                EmailLoginCode.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )

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
        await db.refresh(row)

        return RequestEmailCodeResult(
            email=normalized,
            code=code,
            expires_at=row.expires_at,
            cooldown_seconds=EMAIL_LOGIN_CODE_COOLDOWN_SECONDS,
        )

    @staticmethod
    async def request_email_binding_code(
        db: AsyncSession,
        client_id: int,
        email: str,
    ) -> RequestEmailCodeResult:
        normalized = AuthService._normalize_email(email)
        now = AuthService._utcnow()

        result = await db.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if not client:
            raise AuthError("Client not found")

        if client.email == normalized:
            raise AuthError("Этот email уже привязан к вашему аккаунту.")

        recent_result = await db.execute(
            select(EmailBindingCode)
            .where(
                EmailBindingCode.client_id == client.id,
                EmailBindingCode.email == normalized,
                EmailBindingCode.created_at >= now - timedelta(seconds=EMAIL_LOGIN_CODE_COOLDOWN_SECONDS),
            )
            .order_by(EmailBindingCode.id.desc())
            .limit(1)
        )
        recent = recent_result.scalars().first()
        if recent:
            raise AuthError("Код уже отправлен. Попробуйте чуть позже.")

        await db.execute(
            update(EmailBindingCode)
            .where(
                EmailBindingCode.client_id == client.id,
                EmailBindingCode.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )

        code = AuthService._generate_email_code()
        row = EmailBindingCode(
            client_id=client.id,
            email=normalized,
            code_hash=AuthService._hash_token(code),
            expires_at=now + timedelta(minutes=EMAIL_LOGIN_CODE_TTL_MINUTES),
            attempts=0,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        return RequestEmailCodeResult(
            email=normalized,
            code=code,
            expires_at=row.expires_at,
            cooldown_seconds=EMAIL_LOGIN_CODE_COOLDOWN_SECONDS,
        )

    @staticmethod
    async def send_email_login_code(email: str, code: str) -> None:
        try:
            send_login_code_email(email, code)
        except Exception:
            logger.exception("Failed to send email code to %s", email)
            print(f"[email-auth-fallback] code {code} for {email}")

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

        local_part = normalized.split("@")[0][:64]

        client = Client(
            telegram_id=None,
            full_name=local_part,
            login=None,
            email=normalized,
            status="active",
            created_via="email",
            default_language="ru",
            is_active=False,
            is_paid=False,
        )
        db.add(client)
        await db.commit()
        await db.refresh(client)
        return client

    @staticmethod
    async def merge_clients(
        db: AsyncSession,
        target_client_id: int,
        source_client_id: int,
    ) -> Client:
        if target_client_id == source_client_id:
            result = await db.execute(select(Client).where(Client.id == target_client_id))
            client = result.scalar_one_or_none()
            if not client:
                raise AuthError("Client not found")
            return client

        target_result = await db.execute(select(Client).where(Client.id == target_client_id))
        target = target_result.scalar_one_or_none()
        if not target:
            raise AuthError("Target client not found")

        source_result = await db.execute(select(Client).where(Client.id == source_client_id))
        source = source_result.scalar_one_or_none()
        if not source:
            raise AuthError("Source client not found")

        if target.telegram_id and source.telegram_id and target.telegram_id != source.telegram_id:
            raise AuthError("Нельзя объединить два разных Telegram-аккаунта.")

        source_telegram_id = source.telegram_id
        source_happ_subscription_token = source.happ_subscription_token
        source_happ_subscription_url = source.happ_subscription_url
        source_legacy_login = source.login
        source_legacy_xui_uuid = source.xui_uuid
        source_legacy_xui_email = source.xui_email
        source_legacy_subscription_link = source.subscription_link
        source_full_name = source.full_name
        source_default_language = source.default_language
        source_created_via = source.created_via
        source_last_login_at = source.last_login_at
        source_paid_until = source.paid_until
        source_is_paid = bool(source.is_paid)
        source_is_active = bool(source.is_active)
        source_status = source.status
        source_notes = source.notes
        source_email = source.email

        devices_result = await db.execute(select(Device).where(Device.client_id == source.id))
        for device in devices_result.scalars().all():
            device.client_id = target.id

        sessions_result = await db.execute(select(AppSession).where(AppSession.client_id == source.id))
        for session in sessions_result.scalars().all():
            session.client_id = target.id

        login_codes_result = await db.execute(select(LoginCode).where(LoginCode.client_id == source.id))
        for login_code in login_codes_result.scalars().all():
            login_code.client_id = target.id

        email_login_codes_result = await db.execute(
            select(EmailLoginCode).where(EmailLoginCode.client_id == source.id)
        )
        for email_login_code in email_login_codes_result.scalars().all():
            email_login_code.client_id = target.id

        email_binding_codes_result = await db.execute(
            select(EmailBindingCode).where(EmailBindingCode.client_id == source.id)
        )
        for email_binding_code in email_binding_codes_result.scalars().all():
            email_binding_code.client_id = target.id

        history_result = await db.execute(
            select(SubscriptionHistory).where(SubscriptionHistory.client_id == source.id)
        )
        for history_row in history_result.scalars().all():
            history_row.client_id = target.id

        payments_result = await db.execute(
            select(YooKassaPayment).where(YooKassaPayment.client_id == source.id)
        )
        for payment in payments_result.scalars().all():
            payment.client_id = target.id
            if not payment.telegram_id and source_telegram_id:
                payment.telegram_id = source_telegram_id

        source_accesses_result = await db.execute(
            select(ClientVpnAccess)
            .where(ClientVpnAccess.client_id == source.id)
            .order_by(ClientVpnAccess.node_id.asc(), ClientVpnAccess.id.asc())
        )
        for source_access in source_accesses_result.scalars().all():
            target_access_result = await db.execute(
                select(ClientVpnAccess).where(
                    ClientVpnAccess.client_id == target.id,
                    ClientVpnAccess.node_id == source_access.node_id,
                )
            )
            target_access = target_access_result.scalar_one_or_none()

            if target_access:
                if not target_access.xui_uuid and source_access.xui_uuid:
                    target_access.xui_uuid = source_access.xui_uuid
                if not target_access.xui_email and source_access.xui_email:
                    target_access.xui_email = source_access.xui_email
                if not target_access.subscription_link and source_access.subscription_link:
                    target_access.subscription_link = source_access.subscription_link
                target_access.is_enabled = bool(target_access.is_enabled or source_access.is_enabled)
                target_access.updated_at = AuthService._utcnow()
                await db.delete(source_access)
            else:
                source_access.client_id = target.id
                source_access.updated_at = AuthService._utcnow()

        source.telegram_id = None
        source.email = None
        source.login = None
        source.xui_uuid = None
        source.xui_email = None
        source.subscription_link = None
        source.happ_subscription_token = None
        source.happ_subscription_url = None
        source.updated_at = AuthService._utcnow()

        await db.flush()

        if source_telegram_id and not target.telegram_id:
            target.telegram_id = source_telegram_id

        if not target.email and source_email:
            target.email = source_email

        if source_full_name and (not target.full_name or target.created_via == "email"):
            target.full_name = source_full_name

        if not target.default_language and source_default_language:
            target.default_language = source_default_language

        target.last_login_at = AuthService._max_datetime(target.last_login_at, source_last_login_at)
        target.paid_until = AuthService._max_datetime(target.paid_until, source_paid_until)
        target.is_paid = bool(target.is_paid or source_is_paid)
        target.is_active = bool(target.is_active or source_is_active)
        target.status = AuthService._merge_status(target.status, source_status)
        target.notes = AuthService._merge_notes(target.notes, source_notes)

        if target.created_via != source_created_via and source_created_via:
            target.created_via = "merged"
        elif not target.created_via and source_created_via:
            target.created_via = source_created_via

        if not target.happ_subscription_token and source_happ_subscription_token:
            target.happ_subscription_token = source_happ_subscription_token
            target.happ_subscription_url = source_happ_subscription_url

        if not target.login and source_legacy_login:
            target.login = source_legacy_login
        if not target.xui_uuid and source_legacy_xui_uuid:
            target.xui_uuid = source_legacy_xui_uuid
        if not target.xui_email and source_legacy_xui_email:
            target.xui_email = source_legacy_xui_email
        if not target.subscription_link and source_legacy_subscription_link:
            target.subscription_link = source_legacy_subscription_link

        await AuthService._sync_legacy_access_fields(
            db=db,
            client=target,
            preserve_existing_if_no_pairs=True,
        )

        target.updated_at = AuthService._utcnow()

        logger.info(
            "Merging clients: source_client_id=%s -> target_client_id=%s email=%s telegram_id=%s",
            source_client_id,
            target_client_id,
            target.email,
            target.telegram_id,
        )

        await db.delete(source)
        await db.flush()

        return target

    @staticmethod
    async def confirm_email_binding_code(
        db: AsyncSession,
        client_id: int,
        email: str,
        code: str,
    ) -> ConfirmEmailBindingResult:
        normalized = AuthService._normalize_email(email)
        now = AuthService._utcnow()

        client_result = await db.execute(select(Client).where(Client.id == client_id))
        current_client = client_result.scalar_one_or_none()
        if not current_client:
            raise AuthError("Client not found")

        binding_code_result = await db.execute(
            select(EmailBindingCode)
            .where(
                EmailBindingCode.client_id == current_client.id,
                EmailBindingCode.email == normalized,
                EmailBindingCode.consumed_at.is_(None),
            )
            .order_by(EmailBindingCode.id.desc())
            .limit(1)
        )
        binding_row = binding_code_result.scalars().first()

        if not binding_row:
            raise InvalidLoginCodeError("Код подтверждения не найден")

        if binding_row.expires_at < now:
            binding_row.consumed_at = now
            await db.commit()
            raise ExpiredLoginCodeError("Код подтверждения истек")

        expected_hash = AuthService._hash_token(code.strip())
        if binding_row.code_hash != expected_hash:
            binding_row.attempts += 1
            await db.commit()
            raise InvalidLoginCodeError("Неверный код подтверждения")

        email_client_result = await db.execute(
            select(Client).where(Client.email == normalized)
        )
        email_client = email_client_result.scalar_one_or_none()

        merged = False
        source_client_id: Optional[int] = None
        target_client_id: Optional[int] = None

        if email_client and email_client.id != current_client.id:
            if email_client.telegram_id and current_client.telegram_id and email_client.telegram_id != current_client.telegram_id:
                raise AuthError("Этот email уже привязан к другому Telegram-аккаунту.")

            source_client_id = current_client.id
            target_client_id = email_client.id
            current_client = await AuthService.merge_clients(
                db=db,
                target_client_id=email_client.id,
                source_client_id=current_client.id,
            )
            current_client.email = normalized
            merged = True
        else:
            current_client.email = normalized
            current_client.updated_at = now
            target_client_id = current_client.id

        binding_row.client_id = current_client.id
        binding_row.consumed_at = now
        current_client.last_login_at = AuthService._max_datetime(current_client.last_login_at, now)

        await db.commit()
        await db.refresh(current_client)

        logger.info(
            "Email binding confirmed: client_id=%s email=%s merged=%s source_client_id=%s",
            current_client.id,
            normalized,
            merged,
            source_client_id,
        )

        return ConfirmEmailBindingResult(
            client=current_client,
            merged=merged,
            source_client_id=source_client_id,
            target_client_id=target_client_id,
        )

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
            .limit(1)
        )
        login_row = result.scalars().first()

        if not login_row:
            raise InvalidLoginCodeError("Login code not found")

        if login_row.expires_at < now:
            login_row.consumed_at = now
            await db.commit()
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
