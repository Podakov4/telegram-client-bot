from datetime import datetime, timedelta

from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Client, SubscriptionHistory, YooKassaPayment
from services.client_access import create_vpn_access_for_client

from config import (
    YOOKASSA_AMOUNT_1_MONTH,
    YOOKASSA_AMOUNT_3_MONTHS,
    YOOKASSA_AMOUNT_12_MONTHS,
)
from services.yookassa import (
    create_payment as yk_create_payment,
    get_payment as yk_get_payment,
)


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
            ends_at = client.paid_until + timedelta(days=days)
        else:
            starts_at = now
            ends_at = now + timedelta(days=days)

        client.paid_until = ends_at
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
            ends_at=ends_at,
            notes="payment activation",
        )
        session.add(history)
        await session.commit()

    ok = await create_vpn_access_for_client(telegram_id)
    return ok


async def activate_trial_subscription(
    telegram_id: str,
    days: int = 7,
) -> tuple[bool, str]:
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

    ok = await create_vpn_access_for_client(telegram_id)
    if not ok:
        return False, "Пробный период создан, но доступ не удалось подготовить."

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
    status = payment["status"]

    async with AsyncSessionLocal() as session:
        row = YooKassaPayment(
            external_payment_id=payment_id,
            telegram_id=telegram_id,
            months=months,
            amount=amount,
            status=status,
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

        ok = await activate_subscription(row.telegram_id, row.months)
        if not ok:
            return False, "Оплата прошла, но не удалось активировать подписку."

        row.status = "succeeded"
        row.is_processed = True
        row.processed_at = datetime.utcnow()
        await session.commit()

        return True, "Оплата подтверждена, подписка активирована."


async def confirm_checkout_payment(telegram_id: str, payment_id: str) -> tuple[bool, str]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(YooKassaPayment).where(
                YooKassaPayment.external_payment_id == payment_id,
                YooKassaPayment.telegram_id == telegram_id,
            )
        )
        row = result.scalar_one_or_none()

        if row is None:
            return False, "Платеж не найден."

        if row.is_processed:
            return True, "Этот платеж уже был обработан раньше."

        payment = await yk_get_payment(payment_id)
        row.status = payment.get("status", row.status)
        await session.commit()

        if payment.get("status") != "succeeded":
            return False, f"Текущий статус платежа: {payment.get('status', 'unknown')}"

    return await process_successful_payment(payment_id)