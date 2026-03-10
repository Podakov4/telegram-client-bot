from datetime import datetime, timedelta

from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Client


async def get_expiring_clients(days: int = 3) -> list[Client]:
    now = datetime.utcnow()
    limit_date = now + timedelta(days=days)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(
                Client.is_paid == True,
                Client.is_active == True,
                Client.paid_until.is_not(None),
                Client.paid_until <= limit_date,
            )
        )
        return list(result.scalars().all())


async def get_expired_clients() -> list[Client]:
    now = datetime.utcnow()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(
                Client.paid_until.is_not(None),
                Client.paid_until < now,
                Client.is_active == True,
            )
        )
        return list(result.scalars().all())