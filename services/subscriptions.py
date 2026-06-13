from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import AsyncSessionLocal
from database.models import Client, ClientVpnAccess, Plan
from utils.notes import get_note_int

logger = logging.getLogger(__name__)


@dataclass
class SubscriptionStatus:
    is_active: bool
    is_paid: bool
    paid_until: Optional[datetime]
    is_expired: bool
    days_left: int
    seconds_left: int
    plan_code: Optional[str]
    max_devices: int


class SubscriptionError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.utcnow()



async def get_expiring_clients(days: int = 3) -> list[Client]:
    now = _utcnow()
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
    now = _utcnow()

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
    now = _utcnow()
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
    now = _utcnow()
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
            client.last_expiring_notice_at = _utcnow()
            client.updated_at = _utcnow()
            await session.commit()


async def mark_expired_notice_sent(client_id: int) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if client:
            client.last_expired_notice_at = _utcnow()
            client.updated_at = _utcnow()
            await session.commit()


async def disable_expired_subscriptions() -> int:
    # Imported lazily to avoid a circular import (client_access -> subscriptions).
    from services.client_access import (
        disable_vpn_access_for_client_id,
        is_client_subscription_active,
    )

    now = _utcnow()

    async with AsyncSessionLocal() as session:
        # Candidates = clients whose subscription looks expired, OR who still hold
        # an enabled VPN access row. The second condition is what makes this
        # self-healing: it also catches clients that were flagged inactive in the
        # past but whose VPN access was never actually revoked on the nodes.
        result = await session.execute(
            select(Client.id)
            .outerjoin(ClientVpnAccess, ClientVpnAccess.client_id == Client.id)
            .where(
                or_(
                    and_(
                        Client.is_active == True,
                        Client.paid_until.is_not(None),
                        Client.paid_until <= now,
                    ),
                    ClientVpnAccess.is_enabled == True,
                )
            )
            .distinct()
        )
        candidate_ids = [row[0] for row in result.all()]

    count = 0
    for client_id in candidate_ids:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Client).where(Client.id == client_id)
            )
            client = result.scalar_one_or_none()
            if client is None:
                continue
            # Paid-and-active clients keep their access untouched.
            if is_client_subscription_active(client):
                continue

        # Revoke real VPN access on every node before flipping DB flags, so an
        # expired client can no longer use the VPN.
        try:
            await disable_vpn_access_for_client_id(client_id)
        except Exception:
            logger.exception(
                "Failed to disable VPN access for expired client_id=%s", client_id
            )

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Client).where(Client.id == client_id)
            )
            client = result.scalar_one_or_none()
            if client is None:
                continue
            client.is_active = False
            client.is_paid = False
            client.updated_at = _utcnow()
            await session.commit()
            count += 1

    return count


async def is_subscription_active(client: Client) -> bool:
    if not client:
        return False

    if client.status != "active":
        return False

    if not client.is_active or not client.is_paid:
        return False

    if client.paid_until is None:
        return False

    return client.paid_until > _utcnow()



async def get_plan_by_code(session: AsyncSession, plan_code: str) -> Optional[Plan]:
    result = await session.execute(
        select(Plan).where(
            Plan.code == plan_code,
            Plan.is_active == True,
        )
    )
    return result.scalar_one_or_none()


async def get_max_devices_for_client(
    client: Client,
    db: Optional[AsyncSession] = None,
    default_max_devices: int = 3,
) -> int:
    notes_value = get_note_int(client.notes, "max_devices", 0) or None
    if notes_value:
        return notes_value

    if db and client.notes:
        normalized = [line.strip() for line in client.notes.splitlines() if line.strip()]
        plan_line = next(
            (line for line in normalized if line.lower().startswith("plan_code=")),
            None,
        )
        if plan_line:
            _, plan_code = plan_line.split("=", 1)
            plan = await get_plan_by_code(db, plan_code.strip())
            if plan:
                return plan.max_devices

    return default_max_devices


async def get_client_subscription_status(
    client: Client,
    db: Optional[AsyncSession] = None,
    default_max_devices: int = 3,
) -> SubscriptionStatus:
    now = _utcnow()

    paid_until = client.paid_until
    active = await is_subscription_active(client)
    is_expired = paid_until is None or paid_until <= now

    seconds_left = 0
    days_left = 0

    if paid_until and paid_until > now:
        delta = paid_until - now
        seconds_left = max(int(delta.total_seconds()), 0)
        days_left = max(delta.days, 0)

    plan_code = None
    if client.notes:
        for line in client.notes.splitlines():
            raw = line.strip()
            if raw.lower().startswith("plan_code="):
                _, value = raw.split("=", 1)
                plan_code = value.strip() or None
                break

    max_devices = await get_max_devices_for_client(
        client=client,
        db=db,
        default_max_devices=default_max_devices,
    )

    return SubscriptionStatus(
        is_active=active,
        is_paid=bool(client.is_paid),
        paid_until=paid_until,
        is_expired=is_expired,
        days_left=days_left,
        seconds_left=seconds_left,
        plan_code=plan_code,
        max_devices=max_devices,
    )


async def get_subscription_status_by_client_id(
    client_id: int,
    default_max_devices: int = 3,
) -> Optional[SubscriptionStatus]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id)
        )
        client = result.scalar_one_or_none()
        if not client:
            return None

        return await get_client_subscription_status(
            client=client,
            db=session,
            default_max_devices=default_max_devices,
        )


async def get_subscription_status_by_telegram_id(
    telegram_id: str,
    default_max_devices: int = 3,
) -> Optional[SubscriptionStatus]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == str(telegram_id))
        )
        client = result.scalar_one_or_none()
        if not client:
            return None

        return await get_client_subscription_status(
            client=client,
            db=session,
            default_max_devices=default_max_devices,
        )


def serialize_subscription_status(status: SubscriptionStatus) -> dict:
    return {
        "is_active": status.is_active,
        "is_paid": status.is_paid,
        "paid_until": status.paid_until.isoformat() if status.paid_until else None,
        "is_expired": status.is_expired,
        "days_left": status.days_left,
        "seconds_left": status.seconds_left,
        "plan_code": status.plan_code,
        "max_devices": status.max_devices,
    }