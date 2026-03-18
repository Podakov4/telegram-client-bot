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
from services.auth_service import AuthError, AuthService
from services.device_service import DeviceNotFoundError, DeviceService
from services.payments import (
    activate_trial_subscription,
    create_checkout_payment,
)
from services.subscriptions import get_client_subscription_status, get_expiring_clients

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
        "Вы можете подключиться через Happ, посмотреть данные для подключения, QR-код "
        "или войти в приложение."
    )


def subscription_actions_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Подключить в Happ", callback_data="show_happ_subscription")
    builder.button(text="Показать данные для подключения", callback_data="show_vless_link")
    builder.button(text="Показать QR-код", callback_data="show_vless_qr")
    builder.button(text="Войти в приложение", callback_data="open_app_login_menu")
    builder.button(text="Мои устройства", callback_data="show_my_devices")
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


def payment_checkout_keyboard(payment_url: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="Перейти к оплате", url=payment_url)
    builder.adjust(1)
    return builder.as_markup()


def renewal_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Продлить подписку", callback_data="open_payment_menu")
    builder.adjust(1)
    return builder.as_markup()


def app_login_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Универсальный код", callback_data="app_login_code_any")
    builder.button(text="Android", callback_data="app_login_code_android")
    builder.button(text="iPhone / iPad", callback_data="app_login_code_ios")
    builder.button(text="Windows", callback_data="app_login_code_windows")
    builder.button(text="macOS", callback_data="app_login_code_macos")
    builder.adjust(1)
    return builder.as_markup()


def devices_keyboard(devices: list):
    builder = InlineKeyboardBuilder()
    for device in devices:
        status = "🟢" if device.is_active and not device.is_revoked else "⚪️"
        name = device.device_name or device.platform or "device"
        builder.button(
            text=f"{status} Отключить: {name}",
            callback_data=f"revoke_device:{device.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def format_device_line(device) -> str:
    status = "активно" if device.is_active and not device.is_revoked else "отключено"
    platform = device.platform or "unknown"
    name = device.device_name or "Без названия"
    app_version = device.app_version or "—"
    os_version = device.os_version or "—"
    last_seen = device.last_seen_at.strftime("%Y-%m-%d %H:%M") if device.last_seen_at else "—"

    return (
        f"• <b>{name}</b>\n"
        f"  Платформа: {platform}\n"
        f"  Статус: {status}\n"
        f"  App version: {app_version}\n"
        f"  OS version: {os_version}\n"
        f"  Последняя активность: {last_seen}\n"
        f"  ID: <code>{device.id}</code>"
    )


async def get_client_by_telegram_id(telegram_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def send_devices_message(message: Message, client: Client):
    async with AsyncSessionLocal() as session:
        devices = await DeviceService.list_devices(
            db=session,
            client_id=client.id,
            include_revoked=True,
        )
        limit_info = await DeviceService.get_device_limit_info(
            db=session,
            client=client,
        )
        sub_status = await get_client_subscription_status(client=client, db=session)

    header = (
        "<b>Мои устройства</b>\n\n"
        f"Лимит устройств: <b>{limit_info.active_devices}/{limit_info.max_devices}</b>\n"
        f"Подписка активна: <b>{'да' if sub_status.is_active else 'нет'}</b>\n\n"
    )

    if not devices:
        await message.answer(
            header + "У вас пока нет зарегистрированных устройств.",
            reply_markup=main_reply_keyboard(message.from_user.id),
        )
        return

    body = "\n\n".join(format_device_line(device) for device in devices)

    await message.answer(
        header + body + "\n\nНажмите кнопку ниже, чтобы отключить ненужное устройство.",
        reply_markup=devices_keyboard(devices),
    )


async def send_devices_callback_message(callback: CallbackQuery, client: Client):
    async with AsyncSessionLocal() as session:
        devices = await DeviceService.list_devices(
            db=session,
            client_id=client.id,
            include_revoked=True,
        )
        limit_info = await DeviceService.get_device_limit_info(
            db=session,
            client=client,
        )
        sub_status = await get_client_subscription_status(client=client, db=session)

    header = (
        "<b>Мои устройства</b>\n\n"
        f"Лимит устройств: <b>{limit_info.active_devices}/{limit_info.max_devices}</b>\n"
        f"Подписка активна: <b>{'да' if sub_status.is_active else 'нет'}</b>\n\n"
    )

    if not devices:
        await callback.message.answer(
            header + "У вас пока нет зарегистрированных устройств.",
            reply_markup=main_reply_keyboard(callback.from_user.id),
        )
        await callback.answer()
        return

    body = "\n\n".join(format_device_line(device) for device in devices)

    await callback.message.answer(
        header + body + "\n\nНажмите кнопку ниже, чтобы отключить ненужное устройство.",
        reply_markup=devices_keyboard(devices),
    )
    await callback.answer()


async def start_checkout(callback: CallbackQuery, months: int):
    telegram_id = str(callback.from_user.id)
    full_name = callback.from_user.full_name

    try:
        _, payment_url = await create_checkout_payment(
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
        "3. После успешной оплаты подписка активируется автоматически\n\n"
        "Обычно это происходит без дополнительных действий в боте.",
        reply_markup=payment_checkout_keyboard(payment_url),
    )
    await callback.answer()


async def send_app_login_code_message(
    callback: CallbackQuery,
    platform: str,
):
    telegram_id = str(callback.from_user.id)

    client = await get_client_by_telegram_id(telegram_id)
    if client is None:
        await callback.message.answer("Профиль пока не найден. Нажмите /start")
        await callback.answer()
        return

    async with AsyncSessionLocal() as session:
        try:
            login_code = await AuthService.create_login_code(
                db=session,
                telegram_id=telegram_id,
                platform=platform,
            )
        except AuthError as exc:
            await callback.message.answer(f"Не удалось создать код входа: {exc}")
            await callback.answer()
            return

    platform_label = {
        "any": "любого приложения",
        "android": "Android",
        "ios": "iPhone / iPad",
        "windows": "Windows",
        "macos": "macOS",
    }.get(platform, platform)

    await callback.message.answer(
        "<b>Код для входа в приложение</b>\n\n"
        f"Платформа: <b>{platform_label}</b>\n"
        f"Код: <code>{login_code.code}</code>\n"
        f"Действует до: <b>{login_code.expires_at.strftime('%Y-%m-%d %H:%M:%S')} UTC</b>\n\n"
        "Как использовать:\n"
        "1. Откройте приложение\n"
        "2. Выберите вход по коду\n"
        "3. Введите этот код\n\n"
        "Никому не передавайте код. После использования он станет недействительным.",
        parse_mode="HTML",
        reply_markup=main_reply_keyboard(callback.from_user.id),
    )
    await callback.answer("Код создан")


async def send_app_login_menu_message(message: Message):
    client = await get_client_by_telegram_id(str(message.from_user.id))

    if client is None:
        await message.answer("Профиль пока не найден. Нажмите /start")
        return

    await message.answer(
        "<b>Вход в приложение</b>\n\n"
        "Выберите платформу, для которой нужно создать одноразовый код входа.\n\n"
        "Код действует несколько минут и подходит для входа без пароля.",
        reply_markup=app_login_menu_keyboard(),
    )


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


@router.message(Command("devices"))
@router.message(F.text == "Мои устройства")
async def cmd_devices(message: Message):
    client = await get_client_by_telegram_id(str(message.from_user.id))

    if client is None:
        await message.answer("Профиль пока не найден. Нажмите /start")
        return

    await send_devices_message(message, client)


@router.message(F.text == "Войти в приложение")
async def app_login_menu_from_reply(message: Message):
    await send_app_login_menu_message(message)


@router.callback_query(F.data == "show_my_devices")
async def cb_show_my_devices(callback: CallbackQuery):
    client = await get_client_by_telegram_id(str(callback.from_user.id))

    if client is None:
        await callback.message.answer("Профиль пока не найден. Нажмите /start")
        await callback.answer()
        return

    await send_devices_callback_message(callback, client)


@router.callback_query(F.data.startswith("revoke_device:"))
async def cb_revoke_device(callback: CallbackQuery):
    client = await get_client_by_telegram_id(str(callback.from_user.id))

    if client is None:
        await callback.message.answer("Профиль пока не найден. Нажмите /start")
        await callback.answer()
        return

    try:
        device_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.message.answer("Некорректный идентификатор устройства.")
        await callback.answer()
        return

    async with AsyncSessionLocal() as session:
        try:
            device = await DeviceService.revoke_device(
                db=session,
                client_id=client.id,
                device_id=device_id,
            )
        except DeviceNotFoundError:
            await callback.message.answer("Устройство не найдено.")
            await callback.answer()
            return

    await callback.message.answer(
        "Устройство отключено:\n\n"
        f"<b>{device.device_name or device.platform or 'device'}</b>\n"
        f"ID: <code>{device.id}</code>",
        reply_markup=main_reply_keyboard(callback.from_user.id),
    )
    await callback.answer("Устройство отключено")


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


@router.callback_query(F.data == "open_app_login_menu")
async def cb_open_app_login_menu(callback: CallbackQuery):
    await callback.message.answer(
        "<b>Вход в приложение</b>\n\n"
        "Выберите платформу, для которой нужно создать одноразовый код входа.\n\n"
        "Код действует несколько минут и подходит для входа без пароля.",
        reply_markup=app_login_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "app_login_code_any")
async def cb_app_login_code_any(callback: CallbackQuery):
    await send_app_login_code_message(callback, platform="any")


@router.callback_query(F.data == "app_login_code_android")
async def cb_app_login_code_android(callback: CallbackQuery):
    await send_app_login_code_message(callback, platform="android")


@router.callback_query(F.data == "app_login_code_ios")
async def cb_app_login_code_ios(callback: CallbackQuery):
    await send_app_login_code_message(callback, platform="ios")


@router.callback_query(F.data == "app_login_code_windows")
async def cb_app_login_code_windows(callback: CallbackQuery):
    await send_app_login_code_message(callback, platform="windows")


@router.callback_query(F.data == "app_login_code_macos")
async def cb_app_login_code_macos(callback: CallbackQuery):
    await send_app_login_code_message(callback, platform="macos")


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
            "• Мои устройства\n"
            "• Пробный период 7 дней\n"
            "• Оплата\n"
            "• Войти в приложение\n"
            "• Инструкции\n"
            "• Документы\n"
            "• Поддержка\n\n"
            "В подписке доступны:\n"
            "• Подключить в Happ\n"
            "• Показать данные для подключения\n"
            "• Показать QR-код\n"
            "• Войти в приложение\n"
            "• Мои устройства\n"
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
            "• Мои устройства\n"
            "• Пробный период 7 дней\n"
            "• Оплата\n"
            "• Войти в приложение\n"
            "• Инструкции\n"
            "• Документы\n"
            "• Поддержка\n\n"
            "В подписке доступны:\n"
            "• Подключить в Happ\n"
            "• Показать данные для подключения\n"
            "• Показать QR-код\n"
            "• Войти в приложение\n"
            "• Мои устройства\n"
            "• Продлить подписку\n",
            reply_markup=main_reply_keyboard(message.from_user.id),
        )