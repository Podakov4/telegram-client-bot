from datetime import datetime
from io import BytesIO

import qrcode
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile
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
from services.payments import (
    activate_trial_subscription,
    create_checkout_payment,
    confirm_checkout_payment,
)
from services.subscriptions import get_expiring_clients

router = Router()


def format_profile_text(client: Client) -> str:
    status_text = "активна" if client.is_active else "неактивна"
    paid_text = "да" if client.is_paid else "нет"

    if client.paid_until:
        paid_until_text = client.paid_until.strftime("%Y-%m-%d %H:%M")
        days_left = (client.paid_until - datetime.utcnow()).days
        days_left_text = "истекла" if days_left < 0 else f"{days_left} дн."
    else:
        paid_until_text = "не указано"
        days_left_text = "не указано"

    trial_used = "да" if client.notes and "trial_used=true" in client.notes else "нет"

    return (
        f"<b>Ваш профиль</b>\n\n"
        f"Статус подписки: {status_text}\n"
        f"Оплачено: {paid_text}\n"
        f"Пробный период использован: {trial_used}\n"
        f"Активно до: {paid_until_text}\n"
        f"Осталось: {days_left_text}\n\n"
        f"Имя: {client.full_name or 'не указано'}\n"
        f"Telegram ID: <code>{client.telegram_id}</code>"
    )


def format_subscription_text(client: Client) -> str:
    if not client.subscription_link:
        return (
            "<b>Подписка</b>\n\n"
            "У вас пока нет активного доступа.\n"
            "Сначала активируйте пробный период или оформите подписку."
        )

    return (
        "<b>Подписка</b>\n\n"
        "Доступ подготовлен.\n"
        "Вы можете подключиться через Happ, посмотреть данные для подключения или QR-код."
    )


def subscription_actions_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Подключить в Happ", callback_data="show_happ_subscription")
    builder.button(text="Показать данные для подключения", callback_data="show_vless_link")
    builder.button(text="Показать QR-код", callback_data="show_vless_qr")
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


def payment_checkout_keyboard(payment_url: str, payment_id: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="Перейти к оплате", url=payment_url)
    builder.button(text="Проверить оплату", callback_data=f"check_pay:{payment_id}")
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


async def start_checkout(callback: CallbackQuery, months: int):
    telegram_id = str(callback.from_user.id)
    full_name = callback.from_user.full_name

    try:
        payment_id, payment_url = await create_checkout_payment(
            telegram_id=telegram_id,
            full_name=full_name,
            months=months,
        )
    except Exception as e:
        await callback.message.answer(f"Не удалось создать платеж: {e}")
        await callback.answer()
        return

    await callback.message.answer(
        "Вы оформляете подписку <b>Freeth</b> "
        f"на <b>{months} мес.</b>\n\n"
        "Для продолжения:\n"
        "1. Нажмите «Перейти к оплате»\n"
        "2. Завершите оплату\n"
        "3. Вернитесь в бот\n"
        "4. Нажмите «Проверить оплату»\n\n"
        "После подтверждения подписка активируется автоматически.",
        reply_markup=payment_checkout_keyboard(payment_url, payment_id),
    )
    await callback.answer()


@router.message(Command("profile"))
@router.message(F.text == "Мой профиль")
async def cmd_profile(message: Message):
    client = await get_client_by_telegram_id(str(message.from_user.id))

    if client is None:
        await message.answer("Профиль пока не найден. Нажмите /start")
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
        await message.answer("Профиль пока не найден. Нажмите /start")
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


@router.callback_query(F.data == "show_happ_subscription")
async def cb_show_happ_subscription(callback: CallbackQuery):
    client = await get_client_by_telegram_id(str(callback.from_user.id))

    if client is None or not client.happ_subscription_url:
        await callback.message.answer("Ссылка для Happ пока не подготовлена.")
        await callback.answer()
        return

    await callback.message.answer(
        "Ссылка для подключения в Happ:\n\n"
        f"<code>{client.happ_subscription_url}</code>\n\n"
        "Откройте Happ и импортируйте эту ссылку как подписку.",
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(F.data == "show_vless_link")
async def cb_show_vless_link(callback: CallbackQuery):
    client = await get_client_by_telegram_id(str(callback.from_user.id))

    if client is None or not client.subscription_link:
        await callback.message.answer("Данные для подключения не найдены.")
        await callback.answer()
        return

    await callback.message.answer(
        "Данные для подключения:\n\n"
        f"<code>{client.subscription_link}</code>",
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(F.data == "show_vless_qr")
async def cb_show_vless_qr(callback: CallbackQuery):
    client = await get_client_by_telegram_id(str(callback.from_user.id))

    if client is None or not client.subscription_link:
        await callback.message.answer("Данные для подключения не найдены.")
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
        filename="access_qr.png",
    )

    await callback.message.answer_photo(
        photo,
        caption="QR-код для подключения.",
        reply_markup=main_reply_keyboard(callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(F.data == "open_payment_menu")
async def cb_open_payment_menu(callback: CallbackQuery):
    await callback.message.answer(
        "<b>Freeth</b>\n\n"
        "Цифровой сервис с доступом по подписке.\n\n"
        "Тарифы:\n"
        f"• 1 месяц — {PRICE_1_MONTH}\n"
        f"• 3 месяца — {PRICE_3_MONTHS}\n"
        f"• 12 месяцев — {PRICE_12_MONTHS}\n\n"
        "Также доступен пробный период на 7 дней.\n\n"
        "Выберите подходящий тариф ниже.",
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
            "Доступ подготовлен.",
            reply_markup=subscription_actions_keyboard(),
        )


@router.message(F.text == "Оплата")
async def payment_menu(message: Message):
    await message.answer(
        "<b>Freeth</b>\n\n"
        "Цифровой сервис с доступом по подписке.\n\n"
        "Тарифы:\n"
        f"• 1 месяц — {PRICE_1_MONTH}\n"
        f"• 3 месяца — {PRICE_3_MONTHS}\n"
        f"• 12 месяцев — {PRICE_12_MONTHS}\n\n"
        "Также доступен пробный период на 7 дней.\n\n"
        "Выберите подходящий тариф ниже.",
        reply_markup=payment_keyboard(),
    )


@router.callback_query(F.data == "pay_1_month")
async def cb_pay_1_month(callback: CallbackQuery):
    await start_checkout(callback, months=1)


@router.callback_query(F.data == "pay_3_months")
async def cb_pay_3_months(callback: CallbackQuery):
    await start_checkout(callback, months=3)


@router.callback_query(F.data == "pay_12_months")
async def cb_pay_12_months(callback: CallbackQuery):
    await start_checkout(callback, months=12)


@router.callback_query(F.data.startswith("check_pay:"))
async def cb_check_pay(callback: CallbackQuery):
    payment_id = callback.data.split(":", 1)[1]

    ok, text = await confirm_checkout_payment(
        telegram_id=str(callback.from_user.id),
        payment_id=payment_id,
    )

    await callback.message.answer(
        text,
        reply_markup=main_reply_keyboard(callback.from_user.id),
    )
    await callback.answer()


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


@router.message(F.text == "Помощь")
async def help_message(message: Message):
    if message.from_user.id in ADMIN_IDS:
        await message.answer(
            "Доступные действия:\n"
            "• Мой профиль\n"
            "• Моя подписка\n"
            "• Пробный период 7 дней\n"
            "• Оплата\n"
            "• Инструкции\n"
            "• Документы\n"
            "• Поддержка\n\n"
            "В подписке доступны:\n"
            "• Подключить в Happ\n"
            "• Показать данные для подключения\n"
            "• Показать QR-код\n"
            "• Продлить подписку\n\n"
            "Команды администратора:\n"
            "• /admin — открыть админ-меню\n"
            "• /find [telegram_id | id | имя] — найти клиента\n"
            "• /export_clients — выгрузить клиентов в CSV\n"
            "• /news — создать новость и сделать рассылку\n"
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
            "• Оплата\n"
            "• Инструкции\n"
            "• Документы\n"
            "• Поддержка\n\n"
            "В подписке доступны:\n"
            "• Подключить в Happ\n"
            "• Показать данные для подключения\n"
            "• Показать QR-код\n"
            "• Продлить подписку\n",
            reply_markup=main_reply_keyboard(message.from_user.id),
        )