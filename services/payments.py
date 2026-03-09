from datetime import datetime, timedelta

from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Client
from services.client_access import create_vpn_access_for_client


def add_months_as_days(months: int) -> int:
    if months == 1:
        return 30
    if months == 3:
        return 90
    if months == 12:
        return 365
    return months * 30


async def activate_subscription(telegram_id: str, months: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        client = result.scalar_one_or_none()

        if client is None:
            return False

        now = datetime.utcnow()
        days = add_months_as_days(months)

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


async def deactivate_subscription(telegram_id: str) -> bool:
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