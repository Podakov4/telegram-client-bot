import asyncio
import os
import uuid
from decimal import Decimal, InvalidOperation

import requests

from config import (
    YOOKASSA_SHOP_ID,
    YOOKASSA_SECRET_KEY,
    YOOKASSA_RETURN_URL,
)

YOOKASSA_API_URL = "https://api.yookassa.ru/v3/payments"

# Необязательные переменные окружения для чека
YOOKASSA_RECEIPT_EMAIL = os.getenv("YOOKASSA_RECEIPT_EMAIL", "").strip()
YOOKASSA_TAX_SYSTEM_CODE = os.getenv("YOOKASSA_TAX_SYSTEM_CODE", "").strip()
YOOKASSA_VAT_CODE = int(os.getenv("YOOKASSA_VAT_CODE", "1"))
YOOKASSA_PAYMENT_SUBJECT = os.getenv("YOOKASSA_PAYMENT_SUBJECT", "service").strip()
YOOKASSA_PAYMENT_MODE = os.getenv("YOOKASSA_PAYMENT_MODE", "full_payment").strip()


def _normalize_amount(amount: str) -> str:
    try:
        value = Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as e:
        raise ValueError(f"Некорректная сумма платежа: {amount}") from e
    return format(value, ".2f")


def _build_receipt(item_name: str, amount: str):
    """
    Делает чек опциональным:
    - если YOOKASSA_RECEIPT_EMAIL не задан, receipt не отправляем
    - если задан, отправляем 1 позицию с нейтральным названием услуги
    """
    if not YOOKASSA_RECEIPT_EMAIL:
        return None

    receipt = {
        "customer": {
            "email": YOOKASSA_RECEIPT_EMAIL,
        },
        "items": [
            {
                "description": item_name[:128],
                "quantity": "1.00",
                "amount": {
                    "value": amount,
                    "currency": "RUB",
                },
                "vat_code": YOOKASSA_VAT_CODE,
                "payment_mode": YOOKASSA_PAYMENT_MODE,
                "payment_subject": YOOKASSA_PAYMENT_SUBJECT,
            }
        ],
    }

    if YOOKASSA_TAX_SYSTEM_CODE:
        try:
            receipt["tax_system_code"] = int(YOOKASSA_TAX_SYSTEM_CODE)
        except ValueError:
            pass

    return receipt


def _create_payment_sync(
    amount: str,
    description: str,
    item_name: str,
    telegram_id: str,
    months: int,
):
    normalized_amount = _normalize_amount(amount)

    headers = {
        "Idempotence-Key": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }

    payload = {
        "amount": {
            "value": normalized_amount,
            "currency": "RUB",
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": YOOKASSA_RETURN_URL,
        },
        "description": description[:128],
        "metadata": {
            "telegram_id": str(telegram_id),
            "months": str(months),
            "service": "freeth",
        },
    }

    receipt = _build_receipt(item_name=item_name, amount=normalized_amount)
    if receipt:
        payload["receipt"] = receipt

    response = requests.post(
        YOOKASSA_API_URL,
        json=payload,
        headers=headers,
        auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
        timeout=30,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        raise RuntimeError(
            f"YooKassa create payment failed: "
            f"status={response.status_code}, body={response.text}"
        ) from e

    return response.json()


def _get_payment_sync(payment_id: str):
    response = requests.get(
        f"{YOOKASSA_API_URL}/{payment_id}",
        auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
        timeout=30,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        raise RuntimeError(
            f"YooKassa get payment failed: "
            f"status={response.status_code}, body={response.text}"
        ) from e

    return response.json()


async def create_payment(
    amount: str,
    description: str,
    item_name: str,
    telegram_id: str,
    months: int,
):
    return await asyncio.to_thread(
        _create_payment_sync,
        amount,
        description,
        item_name,
        telegram_id,
        months,
    )


async def get_payment(payment_id: str):
    return await asyncio.to_thread(_get_payment_sync, payment_id)