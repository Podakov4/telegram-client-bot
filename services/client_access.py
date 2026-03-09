from datetime import datetime, timedelta
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Client
from services.vless import VLESSManager


async def ensure_client_exists(telegram_id: str, full_name: str) -> Client:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        client = result.scalar_one_or_none()

        if client is None:
            client = Client(
                telegram_id=telegram_id,
                full_name=full_name,
                is_active=False,
                is_paid=False,
            )
            session.add(client)
            await session.commit()
            await session.refresh(client)

        return client


async def create_vpn_access_for_client(telegram_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        client = result.scalar_one_or_none()

        if client is None:
            return False

        if client.xui_uuid and client.subscription_link:
            return True

        xui_email = client.login or f"user_{client.id}"

        manager = VLESSManager()

        paid_until = datetime.utcnow() + timedelta(days=30)
        paid_until_ts_ms = int(paid_until.timestamp() * 1000)

        created = manager.add_client(
            telegram_id=client.telegram_id,
            full_name=client.full_name or xui_email,
            xui_email=xui_email,
            paid_until_ts_ms=paid_until_ts_ms,
            total_gb=0,
        )
        logger.info("create_vpn_access_for_client result=%s", created)

        if not created:
            return False

        xui_uuid, xui_email, subscription_link = created

        client.login = xui_email
        client.xui_email = xui_email
        client.xui_uuid = xui_uuid
        client.subscription_link = subscription_link
        client.is_active = True
        client.is_paid = True
        client.paid_until = paid_until
        client.updated_at = datetime.utcnow()

        await session.commit()
        return True