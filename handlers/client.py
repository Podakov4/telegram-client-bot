from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command
from sqlalchemy import select
from config import ADMIN_IDS
from services.payments import mark_client_paid, mark_client_unpaid

from database.db import AsyncSessionLocal
from database.models import Client
from services.client_access import create_vpn_access_for_client

router = Router()


def format_profile_text(client: Client) -> str:
    active_text = "Да" if client.is_active else "Нет"
    paid_text = "Да" if client.is_paid else "Нет"
    paid_until_text = (
        client.paid_until.strftime("%Y-%m-%d %H:%M") if client.paid_until else "Не указано"
    )

    return (
        f"Ваш профиль:\n\n"
        f"ID: {client.id}\n"
        f"Telegram ID: {client.telegram_id}\n"
        f"Имя: {client.full_name or 'Не указано'}\n"
        f"Логин: {client.login or 'Не указан'}\n"
        f"UUID: {client.xui_uuid or 'Не назначен'}\n"
        f"Активен: {active_text}\n"
        f"Оплачено: {paid_text}\n"
        f"Оплачено до: {paid_until_text}\n"
    )


def format_subscription_text(client: Client) -> str:
    if not client.subscription_link:
        return (
            "У вас пока нет ссылки подписки.\n"
            "Нажмите /create_access чтобы создать доступ."
        )

    return (
        "Ваша ссылка подписки:\n\n"
        f"{client.subscription_link}\n\n"
        "Скопируйте ее и импортируйте в VPN-клиент."
    )


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    telegram_id = str(message.from_user.id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        client = result.scalar_one_or_none()

    if client is None:
        await message.answer("Профиль не найден. Нажмите /start")
        return

    await message.answer(format_profile_text(client))


@router.message(Command("subscription"))
async def cmd_subscription(message: Message):
    telegram_id = str(message.from_user.id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        client = result.scalar_one_or_none()

    if client is None:
        await message.answer("Профиль не найден. Нажмите /start")
        return

    await message.answer(format_subscription_text(client))


@router.message(Command("create_access"))
async def cmd_create_access(message: Message):
    telegram_id = str(message.from_user.id)

    ok = await create_vpn_access_for_client(telegram_id)

    if not ok:
        await message.answer("Не удалось создать доступ. Проверь настройки 3x-ui.")
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        client = result.scalar_one_or_none()

    await message.answer("Доступ создан.")
    await message.answer(format_subscription_text(client))


@router.callback_query(F.data == "my_profile")
async def cb_my_profile(callback: CallbackQuery):
    telegram_id = str(callback.from_user.id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        client = result.scalar_one_or_none()

    if client is None:
        await callback.message.answer("Профиль не найден. Нажмите /start")
        await callback.answer()
        return

    await callback.message.answer(format_profile_text(client))
    await callback.answer()


@router.callback_query(F.data == "my_subscription")
async def cb_my_subscription(callback: CallbackQuery):
    telegram_id = str(callback.from_user.id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        client = result.scalar_one_or_none()

    if client is None:
        await callback.message.answer("Профиль не найден. Нажмите /start")
        await callback.answer()
        return

    await callback.message.answer(format_subscription_text(client))
    await callback.answer()


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    await callback.message.answer(
        "Команды:\n"
        "/start — регистрация\n"
        "/menu — меню\n"
        "/profile — профиль\n"
        "/subscription — ссылка подписки\n"
        "/create_access — создать VPN-доступ"
    )
    await callback.answer()

@router.message(Command("pay"))
async def cmd_pay(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Недостаточно прав.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /pay <telegram_id>")
        return

    telegram_id = parts[1]
    ok = await mark_client_paid(telegram_id)

    if not ok:
        await message.answer("Клиент не найден.")
        return

    await message.answer(f"Оплата подтверждена для {telegram_id}.")


@router.message(Command("unpay"))
async def cmd_unpay(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Недостаточно прав.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /unpay <telegram_id>")
        return

    telegram_id = parts[1]
    ok = await mark_client_unpaid(telegram_id)

    if not ok:
        await message.answer("Клиент не найден.")
        return

    await message.answer(f"Подписка отключена для {telegram_id}.")