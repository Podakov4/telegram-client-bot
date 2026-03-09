from datetime import datetime, timedelta

from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Client
from services.client_access import create_vpn_access_for_client


async def mark_client_paid(telegram_id: str, days: int = 30) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        client = result.scalar_one_or_none()

        if client is None:
            return False

        now = datetime.utcnow()

        if client.paid_until and client.paid_until > now:
            client.paid_until = client.paid_until + timedelta(days=days)
        else:
            client.paid_until = now + timedelta(days=days)

        client.is_paid = True
        client.is_active = True
        client.updated_at = now

        await session.commit()

    await create_vpn_access_for_client(telegram_id)
    return True


async def mark_client_unpaid(telegram_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        client = result.scalar_one_or_none()

        if client is None:
            return False

        client.is_paid = False
        client.is_active = False
        client.updated_at = datetime.utcnow()

        await session.commit()

    return True