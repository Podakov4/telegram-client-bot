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
                Client.is_active == True,
                Client.paid_until.is_not(None),
                Client.paid_until > now,
                Client.paid_until <= limit_date,
            )
        )
        return list(result.scalars().all())


async def get_expired_clients() -> list[Client]:
    now = datetime.utcnow()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(
                Client.is_active == True,
                Client.paid_until.is_not(None),
                Client.paid_until <= now,
            )
        )
        return list(result.scalars().all())


async def get_expiring_clients_for_notice(days: int = 3, cooldown_hours: int = 20) -> list[Client]:
    now = datetime.utcnow()
    limit_date = now + timedelta(days=days)
    cooldown_date = now - timedelta(hours=cooldown_hours)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(
                Client.is_active == True,
                Client.paid_until.is_not(None),
                Client.paid_until > now,
                Client.paid_until <= limit_date,
            )
        )
        clients = list(result.scalars().all())

        return [
            client for client in clients
            if client.last_expiring_notice_at is None or client.last_expiring_notice_at < cooldown_date
        ]


async def get_expired_clients_for_notice(cooldown_hours: int = 20) -> list[Client]:
    now = datetime.utcnow()
    cooldown_date = now - timedelta(hours=cooldown_hours)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(
                Client.paid_until.is_not(None),
                Client.paid_until <= now,
            )
        )
        clients = list(result.scalars().all())

        return [
            client for client in clients
            if client.last_expired_notice_at is None or client.last_expired_notice_at < cooldown_date
        ]


async def mark_expiring_notice_sent(client_id: int) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if client:
            client.last_expiring_notice_at = datetime.utcnow()
            client.updated_at = datetime.utcnow()
            await session.commit()


async def mark_expired_notice_sent(client_id: int) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if client:
            client.last_expired_notice_at = datetime.utcnow()
            client.updated_at = datetime.utcnow()
            await session.commit()


async def disable_expired_subscriptions() -> int:
    now = datetime.utcnow()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(
                Client.is_active == True,
                Client.paid_until.is_not(None),
                Client.paid_until <= now,
            )
        )
        clients = list(result.scalars().all())

        count = 0
        for client in clients:
            client.is_active = False
            client.is_paid = False
            client.updated_at = now
            count += 1

        if count:
            await session.commit()

        return count