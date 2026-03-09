from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from config import ADMIN_IDS
from database.db import AsyncSessionLocal
from database.models import Client
from keyboards.reply import main_reply_keyboard
from services.client_access import create_vpn_access_for_client
from services.payments import activate_subscription, deactivate_subscription

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
        return "У вас пока нет ссылки подписки.\nСначала оплатите подписку."

    return (
        "Подписка готова.\n\n"
        "Нажмите «Показать ссылку», чтобы скопировать конфиг."
    )


def subscription_actions_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Показать ссылку", callback_data="show_vless_link")
    builder.adjust(1)
    return builder.as_markup()


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

    await message.answer(
        format_profile_text(client),
        reply_markup=main_reply_keyboard(message.from_user.id),
    )


@router.message(Command("subscription"))
@router.message(F.text == "Моя подписка")
async def cmd_subscription(message: Message):
    client = await get_client_by_telegram_id(str(message.from_user.id))

    if client is None:
        await message.answer("Профиль не найден. Нажмите /start")
        return

    if not client.subscription_link:
        await message.answer(
            format_subscription_text(client),
            reply_markup=main_reply_keyboard(message.from_user.id),
        )
        return

    await message.answer(
        format_subscription_text(client),
        reply_markup=subscription_actions_keyboard(),
    )


@router.callback_query(F.data == "show_vless_link")
async def cb_show_vless_link(callback: CallbackQuery):
    client = await get_client_by_telegram_id(str(callback.from_user.id))

    if client is None or not client.subscription_link:
        await callback.message.answer("Ссылка подписки не найдена.")
        await callback.answer()
        return

    await callback.message.answer(
        "Ссылка для копирования:\n\n"
        f"<code>{client.subscription_link}</code>",
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(callback.from_user.id),
    )
    await callback.answer()


@router.message(F.text == "Оплатить 1 месяц")
async def pay_1_month(message: Message):
    ok = await activate_subscription(str(message.from_user.id), months=1)
    if not ok:
        await message.answer("Не удалось активировать подписку.")
        return

    client = await get_client_by_telegram_id(str(message.from_user.id))
    await message.answer(
        "Подписка на 1 месяц активирована.",
        reply_markup=main_reply_keyboard(message.from_user.id),
    )

    if client and client.subscription_link:
        await message.answer(
            "Ссылка готова:",
            reply_markup=subscription_actions_keyboard(),
        )


@router.message(F.text == "Оплатить 3 месяца")
async def pay_3_months(message: Message):
    ok = await activate_subscription(str(message.from_user.id), months=3)
    if not ok:
        await message.answer("Не удалось активировать подписку.")
        return

    client = await get_client_by_telegram_id(str(message.from_user.id))
    await message.answer(
        "Подписка на 3 месяца активирована.",
        reply_markup=main_reply_keyboard(message.from_user.id),
    )

    if client and client.subscription_link:
        await message.answer(
            "Ссылка готова:",
            reply_markup=subscription_actions_keyboard(),
        )


@router.message(F.text == "Оплатить 12 месяцев")
async def pay_12_months(message: Message):
    ok = await activate_subscription(str(message.from_user.id), months=12)
    if not ok:
        await message.answer("Не удалось активировать подписку.")
        return

    client = await get_client_by_telegram_id(str(message.from_user.id))
    await message.answer(
        "Подписка на 12 месяцев активирована.",
        reply_markup=main_reply_keyboard(message.from_user.id),
    )

    if client and client.subscription_link:
        await message.answer(
            "Ссылка готова:",
            reply_markup=subscription_actions_keyboard(),
        )


@router.message(F.text == "Помощь")
async def help_message(message: Message):
    await message.answer(
        "Доступные действия:\n"
        "• Мой профиль\n"
        "• Моя подписка\n"
        "• Оплатить 1 месяц\n"
        "• Оплатить 3 месяца\n"
        "• Оплатить 12 месяцев\n\n"
        "После оплаты подписка активируется автоматически.",
        reply_markup=main_reply_keyboard(message.from_user.id),
    )


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

    await message.answer(
        "Доступ создан.",
        reply_markup=main_reply_keyboard(message.from_user.id),
    )


@router.message(F.text == "⛔ Отключить подписку")
async def unpay_me(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Недостаточно прав.")
        return

    telegram_id = str(message.from_user.id)
    ok = await deactivate_subscription(telegram_id)

    if not ok:
        await message.answer("Не удалось отключить подписку.")
        return

    await message.answer(
        "Подписка отключена.",
        reply_markup=main_reply_keyboard(message.from_user.id),
    )