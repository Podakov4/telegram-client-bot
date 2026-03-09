from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy import select

from config import ADMIN_IDS
from database.db import AsyncSessionLocal
from database.models import Client
from keyboards.reply import main_reply_keyboard
from services.client_access import create_vpn_access_for_client
from services.payments import mark_client_paid, mark_client_unpaid

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
        if client.is_paid:
            return (
                "Оплата отмечена, но ссылка еще не создана.\n"
                "Нажмите «➕ Создать доступ» или попробуйте позже."
            )
        return (
            "У вас пока нет ссылки подписки.\n"
            "Нажмите «Запросить доступ»."
        )

    return (
        "Ваша ссылка подписки:\n\n"
        f"{client.subscription_link}\n\n"
        "Скопируйте ее и импортируйте в VPN-клиент."
    )


async def get_client_by_telegram_id(telegram_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


@router.message(Command("profile"))
@router.message(F.text == "Мой профиль")
async def cmd_profile(message: Message):
    client = await get_client_by_telegram_id(str(message.from_user.id))

    if client is None:
        await message.answer("Профиль не найден. Нажмите /start")
        return

    await message.answer(format_profile_text(client), reply_markup=main_reply_keyboard(message.from_user.id))


@router.message(Command("subscription"))
@router.message(F.text == "Моя подписка")
async def cmd_subscription(message: Message):
    client = await get_client_by_telegram_id(str(message.from_user.id))

    if client is None:
        await message.answer("Профиль не найден. Нажмите /start")
        return

    await message.answer(format_subscription_text(client), reply_markup=main_reply_keyboard(message.from_user.id))


@router.message(F.text == "Запросить доступ")
async def request_access(message: Message):
    await message.answer(
        "Заявка на доступ отправлена.\nПосле подтверждения оплаты и создания доступа ссылка появится в разделе «Моя подписка».",
        reply_markup=main_reply_keyboard(message.from_user.id),
    )


@router.message(F.text == "Помощь")
async def help_message(message: Message):
    await message.answer(
        "Доступные действия:\n"
        "• Мой профиль\n"
        "• Моя подписка\n"
        "• Запросить доступ\n\n"
        "Для администратора также доступны:\n"
        "• ✅ Подтвердить оплату\n"
        "• ➕ Создать доступ\n"
        "• ⛔ Отключить подписку",
        reply_markup=main_reply_keyboard(message.from_user.id),
    )


@router.message(F.text == "✅ Подтвердить оплату")
async def pay_me(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Недостаточно прав.")
        return

    telegram_id = str(message.from_user.id)
    ok = await mark_client_paid(telegram_id)

    if not ok:
        await message.answer("Не удалось подтвердить оплату.")
        return

    await message.answer("Оплата подтверждена.", reply_markup=main_reply_keyboard(message.from_user.id))


@router.message(F.text == "➕ Создать доступ")
async def create_access_me(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Недостаточно прав.")
        return

    telegram_id = str(message.from_user.id)
    ok = await create_vpn_access_for_client(telegram_id)

    if not ok:
        await message.answer("Не удалось создать доступ в 3x-ui.")
        return

    client = await get_client_by_telegram_id(telegram_id)
    await message.answer("Доступ создан.", reply_markup=main_reply_keyboard(message.from_user.id))
    await message.answer(format_subscription_text(client), reply_markup=main_reply_keyboard(message.from_user.id))


@router.message(F.text == "⛔ Отключить подписку")
async def unpay_me(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Недостаточно прав.")
        return

    telegram_id = str(message.from_user.id)
    ok = await mark_client_unpaid(telegram_id)

    if not ok:
        await message.answer("Не удалось отключить подписку.")
        return

    await message.answer("Подписка отключена.", reply_markup=main_reply_keyboard(message.from_user.id))