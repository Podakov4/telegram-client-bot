from datetime import datetime
from io import BytesIO

import qrcode
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from config import (
    ADMIN_IDS,
    PRICE_1_MONTH,
    PRICE_3_MONTHS,
    PRICE_12_MONTHS,
)
from database.db import AsyncSessionLocal
from database.models import Client
from keyboards.reply import main_reply_keyboard
from services.client_access import create_vpn_access_for_client
from services.payments import (
    activate_subscription,
    activate_trial_subscription,
    deactivate_subscription,
)
from services.subscriptions import get_expiring_clients

router = Router()


def format_profile_text(client: Client) -> str:
    active_text = "Да" if client.is_active else "Нет"
    paid_text = "Да" if client.is_paid else "Нет"

    if client.paid_until:
        paid_until_text = client.paid_until.strftime("%Y-%m-%d %H:%M")
        days_left = (client.paid_until - datetime.utcnow()).days
        if days_left < 0:
            days_left_text = "Истекла"
        else:
            days_left_text = f"{days_left} дн."
    else:
        paid_until_text = "Не указано"
        days_left_text = "Не указано"

    trial_used = "Да" if client.notes and "trial_used=true" in client.notes else "Нет"

    return (
        f"Ваш профиль:\n\n"
        f"ID: {client.id}\n"
        f"Telegram ID: {client.telegram_id}\n"
        f"Имя: {client.full_name or 'Не указано'}\n"
        f"Логин: {client.login or 'Не указан'}\n"
        f"UUID: {client.xui_uuid or 'Не назначен'}\n"
        f"Активен: {active_text}\n"
        f"Оплачено: {paid_text}\n"
        f"Пробный использован: {trial_used}\n"
        f"Активно до: {paid_until_text}\n"
        f"Осталось: {days_left_text}\n"
    )


def format_subscription_text(client: Client) -> str:
    if not client.subscription_link:
        return "У вас пока нет ссылки подписки.\nСначала активируйте пробный период или оплатите подписку."

    return "Подписка готова.\n\nВыберите действие ниже."


def subscription_actions_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Показать ссылку", callback_data="show_vless_link")
    builder.button(text="Показать QR", callback_data="show_vless_qr")
    builder.button(text="Продлить подписку", callback_data="open_payment_menu")
    builder.adjust(1)
    return builder.as_markup()


def payment_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text=f"1 месяц — {PRICE_1_MONTH}", callback_data="pay_1_month")
    builder.button(text=f"3 месяца — {PRICE_3_MONTHS}", callback_data="pay_3_months")
    builder.button(text=f"12 месяцев — {PRICE_12_MONTHS}", callback_data="pay_12_months")
    builder.adjust(1)
    return builder.as_markup()


def admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Проверить истекающие", callback_data="admin_check_expiring")
    builder.button(text="Создать доступ себе", callback_data="admin_create_access_me")
    builder.button(text="Отключить свою подписку", callback_data="admin_disable_me")
    builder.adjust(1)
    return builder.as_markup()


def renewal_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Продлить подписку", callback_data="open_payment_menu")
    builder.adjust(1)
    return builder.as_markup()


async def get_client_by_telegram_id(telegram_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def process_payment(
    message_or_callback,
    telegram_id: str,
    months: int,
    user_id: int,
):
    ok = await activate_subscription(telegram_id, months=months)
    if not ok:
        text = "Не удалось активировать подписку."
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.answer(text)
            await message_or_callback.answer()
        else:
            await message_or_callback.answer(text)
        return

    client = await get_client_by_telegram_id(telegram_id)

    if months == 1:
        plan_name = "1 месяц"
    elif months == 3:
        plan_name = "3 месяца"
    elif months == 12:
        plan_name = "12 месяцев"
    else:
        plan_name = f"{months} мес."

    text = f"Тариф «{plan_name}» активирован."

    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.answer(
            text,
            reply_markup=main_reply_keyboard(user_id),
        )
        if client and client.subscription_link:
            await message_or_callback.message.answer(
                "Ссылка готова:",
                reply_markup=subscription_actions_keyboard(),
            )
        await message_or_callback.answer("Оплата активирована")
    else:
        await message_or_callback.answer(
            text,
            reply_markup=main_reply_keyboard(user_id),
        )
        if client and client.subscription_link:
            await message_or_callback.answer(
                "Ссылка готова:",
                reply_markup=subscription_actions_keyboard(),
            )


@router.message(Command("admin"))
async def admin_menu(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Недостаточно прав.")
        return

    await message.answer(
        "Админ-меню:",
        reply_markup=admin_keyboard(),
    )


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


@router.callback_query(F.data == "show_vless_qr")
async def cb_show_vless_qr(callback: CallbackQuery):
    client = await get_client_by_telegram_id(str(callback.from_user.id))

    if client is None or not client.subscription_link:
        await callback.message.answer("Ссылка подписки не найдена.")
        await callback.answer()
        return

    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(client.subscription_link)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    photo = BufferedInputFile(
        buffer.getvalue(),
        filename="vless_qr.png",
    )

    await callback.message.answer_photo(
        photo,
        caption="QR-код вашей подписки.",
        reply_markup=main_reply_keyboard(callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(F.data == "open_payment_menu")
async def cb_open_payment_menu(callback: CallbackQuery):
    await callback.message.answer(
        "Выберите тариф:\n\n"
        f"• 1 месяц — {PRICE_1_MONTH}\n"
        "  Подходит для первого знакомства\n\n"
        f"• 3 месяца — {PRICE_3_MONTHS}\n"
        "  Оптимальный вариант\n\n"
        f"• 12 месяцев — {PRICE_12_MONTHS}\n"
        "  Самый выгодный тариф\n",
        reply_markup=payment_keyboard(),
    )
    await callback.answer()


@router.message(F.text == "Пробный период 7 дней")
async def trial_period(message: Message):
    ok, text = await activate_trial_subscription(str(message.from_user.id), days=7)

    if not ok:
        await message.answer(
            text,
            reply_markup=main_reply_keyboard(message.from_user.id),
        )
        return

    client = await get_client_by_telegram_id(str(message.from_user.id))

    await message.answer(
        "Пробный период на 7 дней активирован.",
        reply_markup=main_reply_keyboard(message.from_user.id),
    )

    if client and client.subscription_link:
        await message.answer(
            "Ссылка готова:",
            reply_markup=subscription_actions_keyboard(),
        )


@router.message(F.text == "Оплата")
async def payment_menu(message: Message):
    await message.answer(
        "Выберите тариф:\n\n"
        f"• 1 месяц — {PRICE_1_MONTH}\n"
        "  Подходит для первого знакомства\n\n"
        f"• 3 месяца — {PRICE_3_MONTHS}\n"
        "  Оптимальный вариант\n\n"
        f"• 12 месяцев — {PRICE_12_MONTHS}\n"
        "  Самый выгодный тариф\n",
        reply_markup=payment_keyboard(),
    )


@router.callback_query(F.data == "pay_1_month")
async def cb_pay_1_month(callback: CallbackQuery):
    await process_payment(
        callback,
        telegram_id=str(callback.from_user.id),
        months=1,
        user_id=callback.from_user.id,
    )


@router.callback_query(F.data == "pay_3_months")
async def cb_pay_3_months(callback: CallbackQuery):
    await process_payment(
        callback,
        telegram_id=str(callback.from_user.id),
        months=3,
        user_id=callback.from_user.id,
    )


@router.callback_query(F.data == "pay_12_months")
async def cb_pay_12_months(callback: CallbackQuery):
    await process_payment(
        callback,
        telegram_id=str(callback.from_user.id),
        months=12,
        user_id=callback.from_user.id,
    )


@router.message(Command("check_expiring"))
async def cmd_check_expiring(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Недостаточно прав.")
        return

    clients = await get_expiring_clients(days=3)

    if not clients:
        await message.answer("Подписок, истекающих в ближайшие 3 дня, нет.")
        return

    lines = ["Подписки, истекающие в ближайшие 3 дня:\n"]
    for client in clients:
        paid_until = (
            client.paid_until.strftime("%Y-%m-%d %H:%M")
            if client.paid_until
            else "Не указано"
        )
        lines.append(
            f"ID={client.id} | tg={client.telegram_id} | "
            f"{client.full_name or 'Без имени'} | до {paid_until}"
        )

    await message.answer("\n".join(lines))


@router.message(Command("preview_expiring"))
async def cmd_preview_expiring(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Недостаточно прав.")
        return

    clients = await get_expiring_clients(days=3)

    if not clients:
        await message.answer("Подписок, истекающих в ближайшие 3 дня, нет.")
        return

    for client in clients:
        paid_until = (
            client.paid_until.strftime("%Y-%m-%d %H:%M")
            if client.paid_until
            else "Не указано"
        )
        await message.answer(
            f"Напоминание для {client.full_name or 'Без имени'}:\n\n"
            f"Подписка истекает: {paid_until}",
            reply_markup=renewal_keyboard(),
        )


@router.callback_query(F.data == "admin_check_expiring")
async def cb_admin_check_expiring(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    clients = await get_expiring_clients(days=3)

    if not clients:
        await callback.message.answer("Подписок, истекающих в ближайшие 3 дня, нет.")
        await callback.answer()
        return

    lines = ["Подписки, истекающие в ближайшие 3 дня:\n"]
    for client in clients:
        paid_until = (
            client.paid_until.strftime("%Y-%m-%d %H:%M")
            if client.paid_until
            else "Не указано"
        )
        lines.append(
            f"ID={client.id} | tg={client.telegram_id} | "
            f"{client.full_name or 'Без имени'} | до {paid_until}"
        )

    await callback.message.answer("\n".join(lines))
    await callback.answer()


@router.callback_query(F.data == "admin_create_access_me")
async def cb_admin_create_access_me(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    telegram_id = str(callback.from_user.id)
    ok = await create_vpn_access_for_client(telegram_id)

    if not ok:
        await callback.message.answer("Не удалось создать доступ.")
        await callback.answer()
        return

    await callback.message.answer("Доступ создан.")
    await callback.answer("Готово")


@router.callback_query(F.data == "admin_disable_me")
async def cb_admin_disable_me(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    telegram_id = str(callback.from_user.id)
    ok = await deactivate_subscription(telegram_id)

    if not ok:
        await callback.message.answer("Не удалось отключить подписку.")
        await callback.answer()
        return

    await callback.message.answer("Подписка отключена.")
    await callback.answer("Готово")


@router.message(F.text == "Помощь")
async def help_message(message: Message):
    if message.from_user.id in ADMIN_IDS:
        await message.answer(
            "Доступные действия:\n"
            "• Мой профиль\n"
            "• Моя подписка\n"
            "• Пробный период 7 дней\n"
            "• Оплата\n\n"
            "В подписке доступны:\n"
            "• Показать ссылку\n"
            "• Показать QR\n"
            "• Продлить подписку\n\n"
            "Команды администратора:\n"
            "• /admin — открыть админ-меню\n"
            "• /find <telegram_id | id | имя> — найти клиента\n"
            "• /check_expiring — показать подписки, истекающие в ближайшие 3 дня\n"
            "• /preview_expiring — посмотреть, как выглядит напоминание о продлении",
            reply_markup=main_reply_keyboard(message.from_user.id),
        )
    else:
        await message.answer(
            "Доступные действия:\n"
            "• Мой профиль\n"
            "• Моя подписка\n"
            "• Пробный период 7 дней\n"
            "• Оплата\n\n"
            "В подписке доступны:\n"
            "• Показать ссылку\n"
            "• Показать QR\n"
            "• Продлить подписку",
            reply_markup=main_reply_keyboard(message.from_user.id),
        )