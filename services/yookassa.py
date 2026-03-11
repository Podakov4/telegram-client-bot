import asyncio
import uuid
import requests

from config import (
    YOOKASSA_SHOP_ID,
    YOOKASSA_SECRET_KEY,
    YOOKASSA_RETURN_URL,
)

YOOKASSA_API_URL = "https://api.yookassa.ru/v3/payments"


def _create_payment_sync(amount: str, description: str, telegram_id: str, months: int):
    headers = {
        "Idempotence-Key": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }

    payload = {
        "amount": {
            "value": amount,
            "currency": "RUB",
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": YOOKASSA_RETURN_URL,
        },
        "description": description[:128],
        "metadata": {
            "telegram_id": telegram_id,
            "months": str(months),
        },
    }

    response = requests.post(
        YOOKASSA_API_URL,
        json=payload,
        headers=headers,
        auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _get_payment_sync(payment_id: str):
    response = requests.get(
        f"{YOOKASSA_API_URL}/{payment_id}",
        auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


async def create_payment(amount: str, description: str, telegram_id: str, months: int):
    return await asyncio.to_thread(
        _create_payment_sync,
        amount,
        description,
        telegram_id,
        months,
    )


async def get_payment(payment_id: str):
    return await asyncio.to_thread(_get_payment_sync, payment_id)