from datetime import datetime, timedelta

from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Client, SubscriptionHistory
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
            starts_at = client.paid_until
            client.paid_until = client.paid_until + timedelta(days=days)
        else:
            starts_at = now
            client.paid_until = now + timedelta(days=days)

        client.is_paid = True
        client.is_active = True
        client.updated_at = now
        client.last_expiring_notice_at = None
        client.last_expired_notice_at = None

        history = SubscriptionHistory(
            client_id=client.id,
            plan_code=f"{months}m",
            is_trial=False,
            starts_at=starts_at,
            ends_at=client.paid_until,
            notes="manual or fake payment activation",
        )
        session.add(history)

        await session.commit()

    await create_vpn_access_for_client(telegram_id)
    return True


async def activate_trial_subscription(telegram_id: str, days: int = 7) -> tuple[bool, str]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        client = result.scalar_one_or_none()

        if client is None:
            return False, "Клиент не найден."

        notes = client.notes or ""
        if "trial_used=true" in notes:
            return False, "Пробный период уже был использован."

        now = datetime.utcnow()
        starts_at = now
        ends_at = now + timedelta(days=days)

        client.paid_until = ends_at
        client.is_paid = False
        client.is_active = True
        client.updated_at = now
        client.last_expiring_notice_at = None
        client.last_expired_notice_at = None

        if notes:
            notes += "\n"
        notes += "trial_used=true"
        client.notes = notes

        history = SubscriptionHistory(
            client_id=client.id,
            plan_code=f"trial_{days}d",
            is_trial=True,
            starts_at=starts_at,
            ends_at=ends_at,
            notes="trial activation",
        )
        session.add(history)

        await session.commit()

    await create_vpn_access_for_client(telegram_id)
    return True, "Пробный период активирован."


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