from __future__ import annotations

from typing import Optional

from aiogram import Bot
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import BOT_TOKEN, SUPPORT_URL
from database.db import AsyncSessionLocal, get_db
from database.models import Client, YooKassaPayment
from services.auth_service import (
    AuthError,
    AuthService,
    ExpiredLoginCodeError,
    InvalidLoginCodeError,
    InvalidRefreshTokenError,
    RevokedSessionError,
)
from services.client_access import (
    get_client_subscription_links_by_client_id,
    get_client_vpn_access_by_client_id,
)
from services.device_service import DeviceNotFoundError, DeviceService
from services.happ_crypto import HappCryptoError, encrypt_happ_subscription_url
from services.payments import create_checkout_payment_for_client, process_successful_payment
from services.subscriptions import (
    get_client_subscription_status,
    serialize_subscription_status,
)

app = FastAPI(title="Freeth API")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# Pydantic schemas
# =========================

class RequestCodePayload(BaseModel):
    telegram_id: str
    platform: Optional[str] = "any"
    device_uid: Optional[str] = None


class RequestEmailCodePayload(BaseModel):
    email: EmailStr


class VerifyEmailCodePayload(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    device_uid: str = Field(..., min_length=3, max_length=255)
    platform: str = Field(..., min_length=2, max_length=32)
    device_name: Optional[str] = Field(default=None, max_length=255)
    app_version: Optional[str] = Field(default=None, max_length=64)
    os_version: Optional[str] = Field(default=None, max_length=64)


class LoginByCodePayload(BaseModel):
    code: str = Field(..., min_length=4, max_length=32)
    device_uid: str = Field(..., min_length=3, max_length=255)
    platform: str = Field(..., min_length=2, max_length=32)
    device_name: Optional[str] = Field(default=None, max_length=255)
    app_version: Optional[str] = Field(default=None, max_length=64)
    os_version: Optional[str] = Field(default=None, max_length=64)


class UpdateProfilePayload(BaseModel):
    email: Optional[str] = Field(default=None, max_length=255)


class RefreshPayload(BaseModel):
    refresh_token: str


class LogoutPayload(BaseModel):
    refresh_token: str


class RevokeDevicePayload(BaseModel):
    device_id: int


class SubscriptionCheckoutPayload(BaseModel):
    months: int = Field(..., ge=1, le=12)


# =========================
# Helpers
# =========================

def build_happ_subscription_body(links: list[str]) -> str:
    cleaned = [line.strip() for line in links if line and line.strip()]
    if not cleaned:
        return ""
    return "\n".join(cleaned) + "\n"


def extract_bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header",
        )

    token = authorization[len(prefix):].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty access token",
        )

    return token


def is_numeric_telegram_id(value: Optional[str]) -> bool:
    return bool(value) and str(value).isdigit()


async def get_current_client(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Client:
    token = extract_bearer_token(authorization)

    try:
        client = await AuthService.get_client_by_access_token(db, token)
    except AuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        )

    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client not found",
        )

    return client


async def get_current_device(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    token = extract_bearer_token(authorization)

    try:
        device = await AuthService.get_device_by_access_token(db, token)
    except AuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        )

    if not device:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Device not found",
        )

    return device


def serialize_client_profile(client: Client) -> dict:
    return {
        "id": client.id,
        "public_id": client.public_id,
        "telegram_id": client.telegram_id,
        "full_name": client.full_name,
        "login": client.login,
        "email": client.email,
        "status": client.status,
        "created_via": client.created_via,
        "default_language": client.default_language,
        "is_active": client.is_active,
        "is_paid": client.is_paid,
        "paid_until": client.paid_until.isoformat() if client.paid_until else None,
        "last_login_at": client.last_login_at.isoformat() if client.last_login_at else None,
        "created_at": client.created_at.isoformat() if client.created_at else None,
        "updated_at": client.updated_at.isoformat() if client.updated_at else None,
    }


# =========================
# Base routes
# =========================

@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/sub/{token}")
async def get_subscription(token: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.happ_subscription_token == token)
        )
        client = result.scalar_one_or_none()

        if client is None:
            raise HTTPException(status_code=404, detail="Subscription not found")

        links = await get_client_subscription_links_by_client_id(client.id)
        if not links:
            raise HTTPException(status_code=404, detail="Access data not found")

        body = build_happ_subscription_body(links)

        return Response(
            content=body,
            media_type="text/plain",
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
                "hide-settings": "1",
                "profile-title": "Freeth",
                "support-url": SUPPORT_URL,
                "profile-update-interval": "1",
            },
        )


@app.get("/sub/{token}/happ")
async def get_happ_import_link(token: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.happ_subscription_token == token)
        )
        client = result.scalar_one_or_none()

        if client is None:
            raise HTTPException(status_code=404, detail="Subscription not found")

        if not client.happ_subscription_url:
            raise HTTPException(status_code=404, detail="Happ subscription URL not found")

        try:
            encrypted_url = encrypt_happ_subscription_url(client.happ_subscription_url)
        except HappCryptoError as e:
            raise HTTPException(status_code=502, detail=str(e))

        return {
            "ok": True,
            "url": encrypted_url,
            "plain_url": client.happ_subscription_url,
        }


# =========================
# App auth routes
# =========================

@app.post("/app/auth/request-code")
async def request_code(
    payload: RequestCodePayload,
    db: AsyncSession = Depends(get_db),
):
    try:
        login_code = await AuthService.create_login_code(
            db=db,
            telegram_id=payload.telegram_id,
            platform=payload.platform,
            device_uid=payload.device_uid,
        )
        return {
            "ok": True,
            "code": login_code.code,
            "expires_at": login_code.expires_at.isoformat(),
            "platform": login_code.platform,
        }
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/app/auth/request-email-code")
async def request_email_code(
    payload: RequestEmailCodePayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await AuthService.request_email_code(
            db=db,
            email=str(payload.email).strip().lower(),
        )

        background_tasks.add_task(
            AuthService.send_email_login_code,
            email=result.email,
            code=result.code,
        )

        return {
            "ok": True,
            "cooldown_seconds": result.cooldown_seconds,
            "expires_at": result.expires_at.isoformat(),
        }
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/app/auth/verify-email-code")
async def verify_email_code(
    payload: VerifyEmailCodePayload,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await AuthService.login_by_email_code(
            db=db,
            email=str(payload.email).strip().lower(),
            code=payload.code.strip(),
            device_uid=payload.device_uid,
            platform=payload.platform,
            device_name=payload.device_name,
            app_version=payload.app_version,
            os_version=payload.os_version,
        )

        return {
            "ok": True,
            "tokens": {
                "access_token": result.tokens.access_token,
                "refresh_token": result.tokens.refresh_token,
                "token_type": result.tokens.token_type,
                "expires_in": result.tokens.expires_in,
            },
            "client": serialize_client_profile(result.client),
            "device": DeviceService.serialize_device(result.device),
        }
    except ExpiredLoginCodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except InvalidLoginCodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/app/auth/login-by-code")
async def login_by_code(
    payload: LoginByCodePayload,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await AuthService.login_by_code(
            db=db,
            code=payload.code,
            device_uid=payload.device_uid,
            platform=payload.platform,
            device_name=payload.device_name,
            app_version=payload.app_version,
            os_version=payload.os_version,
        )

        return {
            "ok": True,
            "tokens": {
                "access_token": result.tokens.access_token,
                "refresh_token": result.tokens.refresh_token,
                "token_type": result.tokens.token_type,
                "expires_in": result.tokens.expires_in,
            },
            "client": serialize_client_profile(result.client),
            "device": DeviceService.serialize_device(result.device),
        }
    except ExpiredLoginCodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except InvalidLoginCodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/app/auth/refresh")
async def refresh_token(
    payload: RefreshPayload,
    db: AsyncSession = Depends(get_db),
):
    try:
        tokens = await AuthService.refresh_tokens(
            db=db,
            refresh_token=payload.refresh_token,
        )
        return {
            "ok": True,
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "token_type": tokens.token_type,
            "expires_in": tokens.expires_in,
        }
    except (InvalidRefreshTokenError, RevokedSessionError, AuthError) as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@app.post("/app/auth/logout")
async def logout(
    payload: LogoutPayload,
    db: AsyncSession = Depends(get_db),
):
    ok = await AuthService.logout(
        db=db,
        refresh_token=payload.refresh_token,
    )
    return {"ok": ok}


@app.post("/app/auth/logout-all")
async def logout_all(
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    revoked = await AuthService.logout_all_for_client(
        db=db,
        client_id=current_client.id,
    )
    return {"ok": True, "revoked_sessions": revoked}


# =========================
# App profile routes
# =========================

@app.get("/me")
async def get_me(
    current_client: Client = Depends(get_current_client),
):
    return {
        "ok": True,
        "client": serialize_client_profile(current_client),
    }


@app.patch("/me/profile")
async def update_my_profile(
    payload: UpdateProfilePayload,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    email = (payload.email or "").strip()

    if email == "":
        current_client.email = None
    else:
        current_client.email = email.lower()

    try:
        await db.commit()
        await db.refresh(current_client)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Этот email уже привязан к другому аккаунту.",
        )
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Не удалось сохранить email.",
        )

    return {
        "ok": True,
        "client": serialize_client_profile(current_client),
    }


@app.get("/me/subscription")
async def get_my_subscription(
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    status_obj = await get_client_subscription_status(
        client=current_client,
        db=db,
    )

    return {
        "ok": True,
        "subscription": serialize_subscription_status(status_obj),
    }


@app.post("/me/subscription/checkout")
async def create_my_subscription_checkout(
    payload: SubscriptionCheckoutPayload,
    current_client: Client = Depends(get_current_client),
):
    payment_id, payment_url = await create_checkout_payment_for_client(
        client_id=current_client.id,
        full_name=current_client.full_name or current_client.email,
        months=payload.months,
    )

    return {
        "ok": True,
        "payment_id": payment_id,
        "payment_url": payment_url,
    }


@app.get("/me/devices")
async def get_my_devices(
    current_client: Client = Depends(get_current_client),
    current_device=Depends(get_current_device),
    db: AsyncSession = Depends(get_db),
):
    await DeviceService.touch_device(
        db=db,
        client_id=current_client.id,
        device_id=current_device.id,
    )

    devices = await DeviceService.list_devices(
        db=db,
        client_id=current_client.id,
        include_revoked=True,
    )
    limit_info = await DeviceService.get_device_limit_info(
        db=db,
        client=current_client,
    )

    return {
        "ok": True,
        "devices": [DeviceService.serialize_device(device) for device in devices],
        "limit": {
            "max_devices": limit_info.max_devices,
            "active_devices": limit_info.active_devices,
            "can_add_more": limit_info.can_add_more,
        },
        "current_device_id": current_device.id,
    }


@app.post("/me/devices/revoke")
async def revoke_my_device(
    payload: RevokeDevicePayload,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    try:
        device = await DeviceService.revoke_device(
            db=db,
            client_id=current_client.id,
            device_id=payload.device_id,
        )
        return {
            "ok": True,
            "device": DeviceService.serialize_device(device),
        }
    except DeviceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# =========================
# VPN routes
# =========================

@app.get("/vpn/access")
async def get_vpn_access(
    current_client: Client = Depends(get_current_client),
):
    access = await get_client_vpn_access_by_client_id(current_client.id)

    if not access:
        raise HTTPException(status_code=404, detail="VPN access not found")

    return {
        "ok": True,
        "access": access,
    }


@app.get("/vpn/subscription-url")
async def get_vpn_subscription_url(
    current_client: Client = Depends(get_current_client),
):
    access = await get_client_vpn_access_by_client_id(current_client.id)

    if not access:
        raise HTTPException(status_code=404, detail="VPN access not found")

    vpn = access.get("vpn", {})
    return {
        "ok": True,
        "subscription_url": vpn.get("subscription_url"),
        "happ_import_url": vpn.get("happ_import_url"),
        "manual_url": vpn.get("manual_url"),
        "manual_urls": vpn.get("manual_urls", []),
        "servers": vpn.get("servers", []),
        "type": vpn.get("type"),
        "supports": vpn.get("supports", []),
    }


# =========================
# YooKassa webhook
# =========================

@app.post("/yookassa/webhook")
async def yookassa_webhook(request: Request):
    payload = await request.json()

    event = payload.get("event")
    obj = payload.get("object", {})
    payment_id = obj.get("id")
    status_value = obj.get("status")

    if event != "payment.succeeded" or not payment_id or status_value != "succeeded":
        return {"ok": True}

    ok, _ = await process_successful_payment(payment_id)

    if ok:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(YooKassaPayment).where(
                    YooKassaPayment.external_payment_id == payment_id
                )
            )
            row = result.scalar_one_or_none()

            if row and is_numeric_telegram_id(row.telegram_id):
                bot = Bot(token=BOT_TOKEN)
                try:
                    await bot.send_message(
                        chat_id=int(row.telegram_id),
                        text=(
                            "Оплата подтверждена автоматически.\n"
                            "Подписка активирована."
                        ),
                    )
                finally:
                    await bot.session.close()

    return {"ok": True}