from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select

from config import (
    YOOKASSA_AMOUNT_1_MONTH,
    YOOKASSA_AMOUNT_3_MONTHS,
    YOOKASSA_AMOUNT_12_MONTHS,
)
from database.db import AsyncSessionLocal
from database.models import Client, SubscriptionHistory, YooKassaPayment
from services.client_access import (
    create_vpn_access_for_client,
    disable_vpn_access_for_client,
)
from services.yookassa import (
    create_payment as yk_create_payment,
    get_payment as yk_get_payment,
)


DEFAULT_MAX_DEVICES_BY_MONTHS = {
    1: 1,
    3: 2,
    12: 3,
}


def add_months_as_days(months: int) -> int:
    if months == 1:
        return 30
    if months == 3:
        return 90
    if months == 12:
        return 365
    return months * 30


def get_amount_by_months(months: int) -> str:
    if months == 1:
        return YOOKASSA_AMOUNT_1_MONTH
    if months == 3:
        return YOOKASSA_AMOUNT_3_MONTHS
    if months == 12:
        return YOOKASSA_AMOUNT_12_MONTHS
    raise ValueError(f"Unsupported months value: {months}")


def build_payment_description(months: int) -> str:
    return f"Freeth — подписка на цифровой сервис, {months} мес."


def build_receipt_item_name(months: int) -> str:
    return f"Подписка на цифровой сервис Freeth — {months} мес."


def get_default_max_devices_for_months(months: int) -> int:
    return DEFAULT_MAX_DEVICES_BY_MONTHS.get(months, 1)


def parse_notes_to_dict(notes: Optional[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    if not notes:
        return result

    for line in notes.splitlines():
        raw = line.strip()
        if not raw or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        result[key.strip()] = value.strip()

    return result


def dump_notes_from_dict(data: dict[str, str]) -> str:
    lines = [f"{key}={value}" for key, value in data.items()]
    return "\n".join(lines)


def upsert_note_value(notes: Optional[str], key: str, value: str) -> str:
    data = parse_notes_to_dict(notes)
    data[key] = value
    return dump_notes_from_dict(data)


async def activate_subscription(
    telegram_id: str,
    months: int,
    *,
    max_devices: Optional[int] = None,
) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == str(telegram_id))
        )
        client = result.scalar_one_or_none()

        if client is None:
            return False

        now = datetime.utcnow()
        days = add_months_as_days(months)
        resolved_max_devices = max_devices or get_default_max_devices_for_months(months)

        if client.paid_until and client.paid_until > now:
            starts_at = client.paid_until
            ends_at = client.paid_until + timedelta(days=days)
        else:
            starts_at = now
            ends_at = now + timedelta(days=days)

        client.paid_until = ends_at
        client.is_paid = True
        client.is_active = True
        client.status = "active"
        client.updated_at = now
        client.last_expiring_notice_at = None
        client.last_expired_notice_at = None

        client.notes = upsert_note_value(client.notes, "plan_code", f"{months}m")
        client.notes = upsert_note_value(client.notes, "max_devices", str(resolved_max_devices))

        history = SubscriptionHistory(
            client_id=client.id,
            plan_code=f"{months}m",
            is_trial=False,
            starts_at=starts_at,
            ends_at=ends_at,
            notes=f"payment activation; max_devices={resolved_max_devices}",
        )
        session.add(history)
        await session.commit()

    ok = await create_vpn_access_for_client(telegram_id)
    return ok


async def activate_trial_subscription(
    telegram_id: str,
    days: int = 7,
    *,
    max_devices: int = 1,
) -> tuple[bool, str]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == str(telegram_id))
        )
        client = result.scalar_one_or_none()

        if client is None:
            return False, "Клиент не найден."

        notes_map = parse_notes_to_dict(client.notes)
        if notes_map.get("trial_used") == "true":
            return False, "Пробный период уже был использован."

        now = datetime.utcnow()
        starts_at = now
        ends_at = now + timedelta(days=days)

        client.paid_until = ends_at
        client.is_paid = False
        client.is_active = True
        client.status = "active"
        client.updated_at = now
        client.last_expiring_notice_at = None
        client.last_expired_notice_at = None

        notes_map["trial_used"] = "true"
        notes_map["plan_code"] = f"trial_{days}d"
        notes_map["max_devices"] = str(max_devices)
        client.notes = dump_notes_from_dict(notes_map)

        history = SubscriptionHistory(
            client_id=client.id,
            plan_code=f"trial_{days}d",
            is_trial=True,
            starts_at=starts_at,
            ends_at=ends_at,
            notes=f"trial activation; max_devices={max_devices}",
        )
        session.add(history)
        await session.commit()

    ok = await create_vpn_access_for_client(telegram_id)
    if not ok:
        return False, "Пробный период создан, но доступ не удалось подготовить."

    return True, "Пробный период активирован."


async def deactivate_subscription(telegram_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == str(telegram_id))
        )
        client = result.scalar_one_or_none()

        if client is None:
            return False

        client.is_paid = False
        client.is_active = False
        client.updated_at = datetime.utcnow()

        await session.commit()

    await disable_vpn_access_for_client(telegram_id)
    return True


async def create_checkout_payment(telegram_id: str, full_name: str | None, months: int):
    amount = get_amount_by_months(months)
    description = build_payment_description(months)
    item_name = build_receipt_item_name(months)

    payment = await yk_create_payment(
        amount=amount,
        description=description,
        item_name=item_name,
        telegram_id=telegram_id,
        months=months,
    )

    payment_id = payment["id"]
    confirmation_url = payment["confirmation"]["confirmation_url"]
    status_value = payment["status"]

    async with AsyncSessionLocal() as session:
        row = YooKassaPayment(
            external_payment_id=payment_id,
            telegram_id=telegram_id,
            months=months,
            amount=amount,
            status=status_value,
            is_processed=False,
        )
        session.add(row)
        await session.commit()

    return payment_id, confirmation_url


async def process_successful_payment(payment_id: str) -> tuple[bool, str]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(YooKassaPayment).where(
                YooKassaPayment.external_payment_id == payment_id,
            )
        )
        row = result.scalar_one_or_none()

        if row is None:
            return False, "Платеж не найден."

        if row.is_processed:
            return True, "Этот платеж уже был обработан раньше."

        ok = await activate_subscription(
            telegram_id=row.telegram_id,
            months=row.months,
        )
        if not ok:
            return False, "Оплата прошла, но не удалось активировать подписку."

        row.status = "succeeded"
        row.is_processed = True
        row.processed_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        await session.commit()

        return True, "Оплата подтверждена, подписка активирована."


async def confirm_checkout_payment(telegram_id: str, payment_id: str) -> tuple[bool, str]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(YooKassaPayment).where(
                YooKassaPayment.external_payment_id == payment_id,
                YooKassaPayment.telegram_id == str(telegram_id),
            )
        )
        row = result.scalar_one_or_none()

        if row is None:
            return False, "Платеж не найден."

        if row.is_processed:
            return True, "Этот платеж уже был обработан раньше."

        payment = await yk_get_payment(payment_id)
        row.status = payment.get("status", row.status)
        row.updated_at = datetime.utcnow()
        await session.commit()

        if payment.get("status") != "succeeded":
            return False, f"Текущий статус платежа: {payment.get('status', 'unknown')}"

    return await process_successful_payment(payment_id)