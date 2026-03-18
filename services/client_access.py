from __future__ import annotations

from datetime import datetime
import logging
import re
import secrets
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import APP_BASE_URL
from database.db import AsyncSessionLocal
from database.models import Client
from services.vless import VLESSManager

logger = logging.getLogger(__name__)


class ClientAccessError(Exception):
    pass


def make_xui_email(telegram_id: str, full_name: str | None, fallback_id: int) -> str:
    base_name = (full_name or f"user_{fallback_id}").lower().strip()
    base_name = base_name.replace(" ", "_")
    base_name = re.sub(r"[^a-zA-Z0-9_а-яА-ЯёЁ]", "", base_name)
    base_name = base_name[:24] if base_name else f"user_{fallback_id}"
    return f"tg_{telegram_id}_{base_name}"


def generate_happ_subscription_token() -> str:
    return secrets.token_urlsafe(24)


def build_happ_subscription_url(token: str) -> str:
    return f"{APP_BASE_URL}/sub/{token}"


def ensure_happ_subscription_for_client(client: Client) -> None:
    if not client.happ_subscription_token:
        client.happ_subscription_token = generate_happ_subscription_token()

    client.happ_subscription_url = build_happ_subscription_url(
        client.happ_subscription_token
    )


def is_client_subscription_active(client: Client) -> bool:
    if client.status != "active":
        return False
    if not client.is_active or not client.is_paid:
        return False
    if not client.paid_until:
        return False
    return client.paid_until > datetime.utcnow()


def serialize_vpn_access(client: Client) -> dict:
    subscription_active = is_client_subscription_active(client)

    return {
        "access": bool(client.xui_uuid and client.subscription_link),
        "subscription_active": subscription_active,
        "expires_at": client.paid_until.isoformat() if client.paid_until else None,
        "vpn": {
            "type": "xray_vless",
            "subscription_url": client.happ_subscription_url,
            "manual_url": client.subscription_link,
            "supports": ["android", "ios", "windows", "macos"],
        },
    }


async def ensure_client_exists(telegram_id: str, full_name: str) -> Client:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == str(telegram_id))
        )
        client = result.scalar_one_or_none()

        if client is None:
            client = Client(
                telegram_id=str(telegram_id),
                full_name=full_name,
                is_active=False,
                is_paid=False,
                created_via="telegram",
                status="active",
            )
            session.add(client)
            await session.commit()
            await session.refresh(client)

        return client


async def get_client_by_telegram_id(telegram_id: str) -> Optional[Client]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == str(telegram_id))
        )
        return result.scalar_one_or_none()


async def get_client_by_id(client_id: int) -> Optional[Client]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id)
        )
        return result.scalar_one_or_none()


async def get_client_vpn_access_by_client_id(client_id: int) -> Optional[dict]:
    client = await get_client_by_id(client_id)
    if not client:
        return None
    return serialize_vpn_access(client)


async def get_client_vpn_access_by_telegram_id(telegram_id: str) -> Optional[dict]:
    client = await get_client_by_telegram_id(telegram_id)
    if not client:
        return None
    return serialize_vpn_access(client)


async def _update_existing_client_access(
    session: AsyncSession,
    client: Client,
) -> bool:
    """
    Если клиент уже существует в 3x-ui, синхронизируем срок действия и включаем его.
    """
    if not client.paid_until:
        logger.warning("Cannot update access: paid_until is empty for client_id=%s", client.id)
        return False

    manager = VLESSManager()
    paid_until_ts_ms = int(client.paid_until.timestamp() * 1000)

    updated = False

    try:
        if client.xui_email:
            updated = manager.enable_client(
                email=client.xui_email,
                expiry_time_ms=paid_until_ts_ms,
                total_gb=0,
            )
    except TypeError:
        # На случай, если сигнатура enable_client чуть отличается в текущем файле vless.py
        logger.exception("enable_client signature mismatch")
        updated = False
    except Exception:
        logger.exception("Failed to enable/update existing client access client_id=%s", client.id)
        updated = False

    if updated:
        if not client.happ_subscription_url:
            ensure_happ_subscription_for_client(client)
        client.updated_at = datetime.utcnow()
        await session.commit()
        return True

    return False


async def create_vpn_access_for_client(telegram_id: str) -> bool:
    logger.info("create_vpn_access_for_client start telegram_id=%s", telegram_id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == str(telegram_id))
        )
        client = result.scalar_one_or_none()

        if client is None:
            logger.warning("Client not found for telegram_id=%s", telegram_id)
            return False

        if not client.paid_until:
            logger.warning("paid_until is empty for telegram_id=%s", telegram_id)
            return False

        ensure_happ_subscription_for_client(client)

        if client.xui_uuid and client.subscription_link:
            logger.info(
                "Client already has access, syncing expiry telegram_id=%s",
                telegram_id,
            )
            synced = await _update_existing_client_access(session, client)
            if synced:
                return True

        xui_email = client.login or make_xui_email(
            telegram_id=client.telegram_id,
            full_name=client.full_name,
            fallback_id=client.id,
        )

        manager = VLESSManager()
        paid_until_ts_ms = int(client.paid_until.timestamp() * 1000)

        created = manager.add_client(
            telegram_id=client.telegram_id,
            full_name=client.full_name or xui_email,
            xui_email=xui_email,
            paid_until_ts_ms=paid_until_ts_ms,
            total_gb=0,
        )

        if not created:
            logger.error("Failed to create client access for telegram_id=%s", telegram_id)
            return False

        xui_uuid, xui_email, subscription_link = created

        client.login = xui_email
        client.xui_email = xui_email
        client.xui_uuid = xui_uuid
        client.subscription_link = subscription_link
        client.updated_at = datetime.utcnow()

        await session.commit()
        return True


async def create_vpn_access_for_client_id(client_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id)
        )
        client = result.scalar_one_or_none()

        if client is None:
            logger.warning("Client not found for client_id=%s", client_id)
            return False

        return await create_vpn_access_for_client(client.telegram_id)


async def disable_vpn_access_for_client(telegram_id: str) -> bool:
    logger.info("disable_vpn_access_for_client start telegram_id=%s", telegram_id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == str(telegram_id))
        )
        client = result.scalar_one_or_none()

        if client is None:
            logger.warning("Client not found for telegram_id=%s", telegram_id)
            return False

        if not client.xui_email and not client.xui_uuid:
            logger.info("Client has no xray access telegram_id=%s", telegram_id)
            return True

        manager = VLESSManager()

        disabled = False
        try:
            if client.xui_email:
                disabled = manager.disable_client(email=client.xui_email)
            elif client.xui_uuid:
                disabled = manager.disable_client(client_uuid=client.xui_uuid)
        except TypeError:
            logger.exception("disable_client signature mismatch")
            disabled = False
        except Exception:
            logger.exception("Failed to disable VPN access for telegram_id=%s", telegram_id)
            disabled = False

        if disabled:
            client.updated_at = datetime.utcnow()
            await session.commit()
            return True

        return False


async def disable_vpn_access_for_client_id(client_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id)
        )
        client = result.scalar_one_or_none()

        if client is None:
            logger.warning("Client not found for client_id=%s", client_id)
            return False

        return await disable_vpn_access_for_client(client.telegram_id)


async def sync_vpn_access_for_client(telegram_id: str) -> bool:
    """
    Синхронизирует доступ с текущим состоянием подписки:
    - если подписка активна -> создаём/обновляем доступ
    - если подписка истекла -> отключаем доступ
    """
    client = await get_client_by_telegram_id(telegram_id)
    if not client:
        return False

    if is_client_subscription_active(client):
        return await create_vpn_access_for_client(telegram_id)

    return await disable_vpn_access_for_client(telegram_id)