from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Response, Request
from sqlalchemy import select

from aiogram import Bot

from config import SUPPORT_URL, BOT_TOKEN
from database.db import AsyncSessionLocal
from database.models import Client, YooKassaPayment
from services.payments import process_successful_payment

app = FastAPI(title="Freeth API")


def to_expire_unix(dt: datetime | None) -> int:
    if not dt:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def build_happ_subscription_body(client: Client) -> str:
    expire = to_expire_unix(client.paid_until)

    lines = [
        "#profile-title: Freeth",
        "#profile-update-interval: 4",
        f"#support-url: {SUPPORT_URL}",
        "#sub-info-color: blue",
        "#sub-info-text: Поддержка и управление доступом Freeth",
        "#sub-info-button-text: Поддержка",
        f"#sub-info-button-link: {SUPPORT_URL}",
        "#sub-expire: 1",
        "#sub-expire-button-link: https://t.me/youFreethBot",
        "#subscriptions-collapse: 0",
        "#subscriptions-expand-now: 1",
        f"#subscription-userinfo: upload=0; download=0; total=0; expire={expire}",
        "",
    ]

    if client.subscription_link:
        lines.append(client.subscription_link)

    return "\n".join(lines) + "\n"


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/sub/{token}")
async def get_subscription(token: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.happ_subscription_token == token)
        )
        client = result.scalar_one_or_none()

        if client is None:
            raise HTTPException(status_code=404, detail="Subscription not found")

        if not client.subscription_link:
            raise HTTPException(status_code=404, detail="Access data not found")

        body = build_happ_subscription_body(client)

        return Response(
            content=body,
            media_type="text/plain",
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Content-Disposition": f'attachment; filename="freeth-{client.id}.txt"',
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
                "profile-title": "Freeth",
                "support-url": SUPPORT_URL,
            },
        )


@app.post("/yookassa/webhook")
async def yookassa_webhook(request: Request):
    payload = await request.json()

    event = payload.get("event")
    obj = payload.get("object", {})
    payment_id = obj.get("id")
    status = obj.get("status")

    if event != "payment.succeeded" or not payment_id or status != "succeeded":
        return {"ok": True}

    ok, _ = await process_successful_payment(payment_id)

    if ok:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(YooKassaPayment).where(
                    YooKassaPayment.external_payment_id == payment_id
                )
            )
            row = result.scalar_one_or_none()

            if row:
                bot = Bot(token=BOT_TOKEN)
                try:
                    await bot.send_message(
                        chat_id=int(row.telegram_id),
                        text=(
                            "Оплата подтверждена автоматически.\n"
                            "Подписка активирована."
                        ),
                    )
                finally:
                    await bot.session.close()

    return {"ok": True}