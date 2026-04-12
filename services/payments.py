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
    create_vpn_access_for_client_id,
    disable_vpn_access_for_client_id,
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

REFERRAL_BONUS_DAYS = 20


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


async def _get_client_by_id(client_id: int) -> Client | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id)
        )
        return result.scalar_one_or_none()


async def _get_client_by_telegram_id(telegram_id: str) -> Client | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == str(telegram_id))
        )
        return result.scalar_one_or_none()


async def grant_referral_bonus_if_eligible(
    session,
    *,
    referred_client_id: int | None,
    rewarded_at: datetime,
) -> int | None:
    if referred_client_id is None:
        return None

    result = await session.execute(
        select(Client).where(Client.id == referred_client_id)
    )
    referred_client = result.scalar_one_or_none()

    if referred_client is None:
        return None

    if referred_client.referrer_client_id is None:
        return None

    if referred_client.referral_reward_granted_at is not None:
        return None

    if referred_client.referrer_client_id == referred_client.id:
        return None

    result = await session.execute(
        select(Client).where(Client.id == referred_client.referrer_client_id)
    )
    referrer = result.scalar_one_or_none()

    if referrer is None:
        return None

    if referrer.paid_until and referrer.paid_until > rewarded_at:
        starts_at = referrer.paid_until
        ends_at = referrer.paid_until + timedelta(days=REFERRAL_BONUS_DAYS)
    else:
        starts_at = rewarded_at
        ends_at = rewarded_at + timedelta(days=REFERRAL_BONUS_DAYS)

    referrer.paid_until = ends_at
    referrer.is_active = True
    referrer.is_paid = True
    referrer.status = "active"
    referrer.updated_at = rewarded_at
    referrer.last_expiring_notice_at = None
    referrer.last_expired_notice_at = None
    referrer.referral_bonus_days_total = (referrer.referral_bonus_days_total or 0) + REFERRAL_BONUS_DAYS

    referred_client.referral_reward_granted_at = rewarded_at
    referred_client.updated_at = rewarded_at

    history = SubscriptionHistory(
        client_id=referrer.id,
        plan_code=f"referral_bonus_{REFERRAL_BONUS_DAYS}d",
        is_trial=False,
        starts_at=starts_at,
        ends_at=ends_at,
        notes=f"referral bonus; referred_client_id={referred_client.id}",
    )
    session.add(history)

    return referrer.id


async def activate_subscription_by_client_id(
    client_id: int,
    months: int,
    *,
    max_devices: Optional[int] = None,
) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id)
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

    ok = await create_vpn_access_for_client_id(client_id)
    return ok


async def activate_subscription(
    telegram_id: str,
    months: int,
    *,
    max_devices: Optional[int] = None,
) -> bool:
    client = await _get_client_by_telegram_id(telegram_id)
    if client is None:
        return False
    return await activate_subscription_by_client_id(
        client_id=client.id,
        months=months,
        max_devices=max_devices,
    )


async def activate_trial_subscription_by_client_id(
    client_id: int,
    days: int = 7,
    *,
    max_devices: int = 1,
) -> tuple[bool, str]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id)
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

    ok = await create_vpn_access_for_client_id(client_id)
    if not ok:
        return False, "Пробный период создан, но доступ не удалось подготовить."

    return True, "Пробный период активирован."


async def activate_trial_subscription(
    telegram_id: str,
    days: int = 7,
    *,
    max_devices: int = 1,
) -> tuple[bool, str]:
    client = await _get_client_by_telegram_id(telegram_id)
    if client is None:
        return False, "Клиент не найден."

    return await activate_trial_subscription_by_client_id(
        client_id=client.id,
        days=days,
        max_devices=max_devices,
    )


async def deactivate_subscription_by_client_id(client_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id)
        )
        client = result.scalar_one_or_none()

        if client is None:
            return False

        client.is_paid = False
        client.is_active = False
        client.updated_at = datetime.utcnow()

        await session.commit()

    await disable_vpn_access_for_client_id(client_id)
    return True


async def deactivate_subscription(telegram_id: str) -> bool:
    client = await _get_client_by_telegram_id(telegram_id)
    if client is None:
        return False
    return await deactivate_subscription_by_client_id(client.id)


async def create_checkout_payment_for_client(
    client_id: int,
    full_name: str | None,
    months: int,
):
    client = await _get_client_by_id(client_id)
    if client is None:
        raise ValueError("Client not found")

    amount = get_amount_by_months(months)
    description = build_payment_description(months)
    item_name = build_receipt_item_name(months)

    payment_customer_ref = client.telegram_id or f"client:{client.id}"

    payment = await yk_create_payment(
        amount=amount,
        description=description,
        item_name=item_name,
        telegram_id=payment_customer_ref,
        months=months,
    )

    payment_id = payment["id"]
    confirmation_url = payment["confirmation"]["confirmation_url"]
    print("YooKassa confirmation_url:", confirmation_url)
    status_value = payment["status"]

    async with AsyncSessionLocal() as session:
        row = YooKassaPayment(
            external_payment_id=payment_id,
            client_id=client.id,
            telegram_id=client.telegram_id,
            months=months,
            amount=amount,
            status=status_value,
            is_processed=False,
        )
        session.add(row)
        await session.commit()

    return payment_id, confirmation_url


async def create_checkout_payment(telegram_id: str, full_name: str | None, months: int):
    client = await _get_client_by_telegram_id(telegram_id)
    if client is None:
        raise ValueError("Client not found")

    return await create_checkout_payment_for_client(
        client_id=client.id,
        full_name=full_name,
        months=months,
    )


async def process_successful_payment(payment_id: str) -> tuple[bool, str]:
    bonus_referrer_client_id: int | None = None

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

        target_client_id = row.client_id
        if target_client_id is None and row.telegram_id:
            target_client = await _get_client_by_telegram_id(row.telegram_id)
            target_client_id = target_client.id if target_client else None

        if row.client_id is not None:
            ok = await activate_subscription_by_client_id(
                client_id=row.client_id,
                months=row.months,
            )
        elif row.telegram_id:
            ok = await activate_subscription(
                telegram_id=row.telegram_id,
                months=row.months,
            )
        else:
            ok = False

        if not ok:
            return False, "Оплата прошла, но не удалось активировать подписку."

        processed_at = datetime.utcnow()
        bonus_referrer_client_id = await grant_referral_bonus_if_eligible(
            session,
            referred_client_id=target_client_id,
            rewarded_at=processed_at,
        )

        row.status = "succeeded"
        row.is_processed = True
        row.processed_at = processed_at
        row.updated_at = processed_at
        await session.commit()

    if bonus_referrer_client_id is not None:
        await create_vpn_access_for_client_id(bonus_referrer_client_id)

    return True, "Оплата подтверждена, подписка активирована."


async def confirm_checkout_payment_for_client(
    client_id: int,
    payment_id: str,
) -> tuple[bool, str]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(YooKassaPayment).where(
                YooKassaPayment.external_payment_id == payment_id,
                YooKassaPayment.client_id == client_id,
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


async def confirm_checkout_payment(telegram_id: str, payment_id: str) -> tuple[bool, str]:
    client = await _get_client_by_telegram_id(telegram_id)
    if client is None:
        return False, "Платеж не найден."

    return await confirm_checkout_payment_for_client(
        client_id=client.id,
        payment_id=payment_id,
    )