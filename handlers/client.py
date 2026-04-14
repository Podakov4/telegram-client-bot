from datetime import datetime
from io import BytesIO
import re

import qrcode
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    Message,
    SwitchInlineQueryChosenChat,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select

from config import (
    ADMIN_IDS,
    PRICE_1_MONTH,
    PRICE_3_MONTHS,
    PRICE_12_MONTHS,
)
from database.db import AsyncSessionLocal
from database.models import Client
from handlers.instructions import instructions_keyboard
from keyboards.reply import main_reply_keyboard
from services.auth_service import (
    AuthError,
    AuthService,
    ExpiredLoginCodeError,
    InvalidLoginCodeError,
)
from services.client_access import build_happ_import_url
from services.device_service import DeviceNotFoundError, DeviceService
from services.payments import activate_trial_subscription, create_checkout_payment
from services.subscriptions import get_client_subscription_status, get_expiring_clients

router = Router()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
REFERRAL_BONUS_DAYS = 20


class EmailBindingStates(StatesGroup):
    waiting_for_email = State()
    waiting_for_code = State()


def client_has_trial_used(client: Client | None) -> bool:
    return bool(client and client.notes and "trial_used=true" in client.notes)


def client_has_active_access(client: Client | None) -> bool:
    if client is None:
        return False

    if client.is_active and client.subscription_link:
        return True

    if client.paid_until and client.paid_until > datetime.utcnow() and client.subscription_link:
        return True

    return False


def build_reply_keyboard_for_client(client: Client | None, user_id: int):
    return main_reply_keyboard(
        user_id,
        has_active_access=client_has_active_access(client),
        trial_used=client_has_trial_used(client),
    )


def format_access_text(client: Client, *, active_devices: int, max_devices: int, is_active: bool) -> str:
    status_text = "активен" if is_active else "не активен"

    if client.paid_until:
        paid_until_text = client.paid_until.strftime("%Y-%m-%d %H:%M")
        days_left = (client.paid_until - datetime.utcnow()).days
        days_left_text = "истек" if days_left < 0 else f"{days_left} дн."
    else:
        paid_until_text = "не указано"
        days_left_text = "—"

    trial_text = "использован" if client_has_trial_used(client) else "доступен"
    email_text = getattr(client, "email", None) or "не привязан"

    if is_active:
        intro_text = "Доступ активен. Ниже выберите нужное действие."
    else:
        intro_text = (
            "Сейчас активного доступа нет. Вы можете попробовать 7 дней или оформить подписку."
        )

    return (
        "<b>Мой доступ</b>\n\n"
        f"Статус: <b>{status_text}</b>\n"
        f"Доступ до: <b>{paid_until_text}</b>\n"
        f"Осталось: <b>{days_left_text}</b>\n"
        f"Пробный период: <b>{trial_text}</b>\n"
        f"Email: <b>{email_text}</b>\n"
        f"Устройства: <b>{active_devices}/{max_devices}</b>\n\n"
        f"{intro_text}"
    )


def access_actions_keyboard(client: Client):
    builder = InlineKeyboardBuilder()
    has_access = client_has_active_access(client)
    trial_used = client_has_trial_used(client)

    if has_access:
        if client.happ_subscription_url:
            builder.button(text="Подключить в Happ", callback_data="show_happ_subscription")
        if client.subscription_link:
            builder.button(
                text="Показать данные для подключения",
                callback_data="show_vless_link",
            )
            builder.button(text="Показать QR-код", callback_data="show_vless_qr")
        builder.button(text="Войти в приложение", callback_data="open_app_login_menu")
        builder.button(text="Мои устройства", callback_data="show_my_devices")
        builder.button(
            text="Изменить email" if client.email else "Привязать email",
            callback_data="bind_email_start",
        )
        builder.button(text="Продлить доступ", callback_data="open_payment_menu")
    else:
        if not trial_used:
            builder.button(text="Попробовать 7 дней", callback_data="activate_trial")
        builder.button(text="Продлить доступ", callback_data="open_payment_menu")
        builder.button(
            text="Изменить email" if client.email else "Привязать email",
            callback_data="bind_email_start",
        )
        builder.button(text="Как подключить", callback_data="open_instructions_from_access")

    builder.adjust(1)
    return builder.as_markup()


def trial_onboarding_keyboard(client: Client):
    builder = InlineKeyboardBuilder()
    if client.happ_subscription_url:
        builder.button(text="Подключить в Happ", callback_data="show_happ_subscription")
    if client.subscription_link:
        builder.button(text="Показать QR-код", callback_data="show_vless_qr")
        builder.button(
            text="Данные для подключения",
            callback_data="show_vless_link",
        )
    builder.button(text="Как подключить", callback_data="open_instructions_from_access")
    builder.button(text="Войти в приложение", callback_data="open_app_login_menu")
    builder.button(
        text="Изменить email" if client.email else "Привязать email",
        callback_data="bind_email_start",
    )
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
    builder.button(text="Продлить доступ", callback_data="open_payment_menu")
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


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(_normalize_email(value)))




def build_referral_link(bot_username: str, referral_code: str) -> str:
    return f"https://t.me/{bot_username}?start=ref_{referral_code}"


def format_referral_program_text(
    *,
    referral_link: str,
    invited_count: int,
    rewarded_count: int,
    bonus_days_total: int,
    recent_referrals: list[Client],
) -> str:
    lines = [
        "<b>Пригласить друга</b>",
        "",
        f"Поделитесь своей ссылкой с другом и получите <b>+{REFERRAL_BONUS_DAYS} дней</b> после его первой успешной оплаты.",
        "",
        "<b>Статистика</b>",
        f"• Пришли по ссылке: <b>{invited_count}</b>",
        f"• Купили подписку: <b>{rewarded_count}</b>",
        f"• Начислено дней: <b>{bonus_days_total}</b>",
        "",
        "<b>Ссылка для приглашения</b>",
        f"<code>{referral_link}</code>",
    ]

    if recent_referrals:
        lines.extend(["", "<b>Последние приглашения</b>"])
        for referral in recent_referrals:
            referral_name = referral.full_name or f"ID {referral.id}"
            paid_mark = " — оплата засчитана" if referral.referral_reward_granted_at else ""
            lines.append(f"• {referral_name}{paid_mark}")

    lines.extend([
        "",
        "Нажмите кнопку ниже, чтобы выбрать контакт и отправить ссылку сразу из Telegram."
    ])
    return "\n".join(lines)


def referral_share_keyboard() -> object:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Отправить ссылку другу ↗️",
        switch_inline_query_chosen_chat=SwitchInlineQueryChosenChat(
            query="share_referral",
            allow_user_chats=True,
            allow_bot_chats=False,
            allow_group_chats=True,
            allow_channel_chats=False,
        ),
    )
    builder.adjust(1)
    return builder.as_markup()


async def get_referral_stats(client_id: int) -> tuple[int, int, list[Client]]:
    async with AsyncSessionLocal() as session:
        invited_count = await session.scalar(
            select(func.count()).select_from(Client).where(Client.referrer_client_id == client_id)
        )
        rewarded_count = await session.scalar(
            select(func.count()).select_from(Client).where(
                Client.referrer_client_id == client_id,
                Client.referral_reward_granted_at.is_not(None),
            )
        )
        result = await session.execute(
            select(Client)
            .where(Client.referrer_client_id == client_id)
            .order_by(Client.referral_joined_at.desc().nullslast(), Client.id.desc())
            .limit(5)
        )
        recent_referrals = list(result.scalars().all())

    return invited_count or 0, rewarded_count or 0, recent_referrals


async def get_client_by_telegram_id(telegram_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def send_access_message(message: Message, client: Client):
    async with AsyncSessionLocal() as session:
        limit_info = await DeviceService.get_device_limit_info(db=session, client=client)
        sub_status = await get_client_subscription_status(client=client, db=session)

    await message.answer(
        format_access_text(
            client,
            active_devices=limit_info.active_devices,
            max_devices=limit_info.max_devices,
            is_active=sub_status.is_active or client_has_active_access(client),
        ),
        reply_markup=access_actions_keyboard(client),
    )


async def send_devices_message(message: Message, client: Client):
    async with AsyncSessionLocal() as session:
        devices = await DeviceService.list_devices(
            db=session,
            client_id=client.id,
            include_revoked=True,
        )
        limit_info = await DeviceService.get_device_limit_info(db=session, client=client)
        sub_status = await get_client_subscription_status(client=client, db=session)

    header = (
        "<b>Мои устройства</b>\n\n"
        f"Лимит устройств: <b>{limit_info.active_devices}/{limit_info.max_devices}</b>\n"
        f"Подписка активна: <b>{'да' if sub_status.is_active else 'нет'}</b>\n\n"
    )

    if not devices:
        await message.answer(
            header + "У вас пока нет зарегистрированных устройств.",
            reply_markup=build_reply_keyboard_for_client(client, message.from_user.id),
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
        limit_info = await DeviceService.get_device_limit_info(db=session, client=client)
        sub_status = await get_client_subscription_status(client=client, db=session)

    header = (
        "<b>Мои устройства</b>\n\n"
        f"Лимит устройств: <b>{limit_info.active_devices}/{limit_info.max_devices}</b>\n"
        f"Подписка активна: <b>{'да' if sub_status.is_active else 'нет'}</b>\n\n"
    )

    if not devices:
        await callback.message.answer(
            header + "У вас пока нет зарегистрированных устройств.",
            reply_markup=build_reply_keyboard_for_client(client, callback.from_user.id),
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
    except Exception as exc:
        await callback.message.answer(f"Не удалось создать платеж: {exc}")
        await callback.answer()
        return

    await callback.message.answer(
        "Вы оформляете доступ <b>Freeth</b> "
        f"на <b>{months} мес.</b>\n\n"
        "Для продолжения:\n"
        "1. Нажмите «Перейти к оплате»\n"
        "2. Завершите оплату\n"
        "3. После успешной оплаты доступ активируется автоматически\n\n"
        "Обычно это происходит без дополнительных действий в боте.",
        reply_markup=payment_checkout_keyboard(payment_url),
    )
    await callback.answer()


async def send_app_login_code_message(callback: CallbackQuery, platform: str):
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
        reply_markup=build_reply_keyboard_for_client(client, callback.from_user.id),
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


@router.message(EmailBindingStates.waiting_for_email)
async def process_email_binding_email(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() == "отмена":
        await state.clear()
        client = await get_client_by_telegram_id(str(message.from_user.id))
        await message.answer(
            "Привязка email отменена.",
            reply_markup=build_reply_keyboard_for_client(client, message.from_user.id),
        )
        return

    client = await get_client_by_telegram_id(str(message.from_user.id))
    if client is None:
        await state.clear()
        await message.answer("Профиль пока не найден. Нажмите /start")
        return

    email = _normalize_email(message.text or "")
    if not _is_valid_email(email):
        await message.answer(
            "Введите корректный email.\n\n"
            "Например: user@example.com\n"
            "Или напишите «Отмена»."
        )
        return

    async with AsyncSessionLocal() as session:
        try:
            result = await AuthService.request_email_binding_code(
                db=session,
                client_id=client.id,
                email=email,
            )
        except AuthError as exc:
            await message.answer(str(exc))
            return

    await AuthService.send_email_login_code(result.email, result.code)

    await state.update_data(binding_email=result.email)
    await state.set_state(EmailBindingStates.waiting_for_code)

    await message.answer(
        "Код подтверждения отправлен на email.\n\n"
        "Введите 6 цифр из письма.\n"
        "Если хотите прервать, напишите «Отмена»."
    )


@router.message(EmailBindingStates.waiting_for_code)
async def process_email_binding_code(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() == "отмена":
        await state.clear()
        client = await get_client_by_telegram_id(str(message.from_user.id))
        await message.answer(
            "Подтверждение email отменено.",
            reply_markup=build_reply_keyboard_for_client(client, message.from_user.id),
        )
        return

    client = await get_client_by_telegram_id(str(message.from_user.id))
    if client is None:
        await state.clear()
        await message.answer("Профиль пока не найден. Нажмите /start")
        return

    data = await state.get_data()
    email = data.get("binding_email")
    code = (message.text or "").strip()

    if not email:
        await state.clear()
        await message.answer("Сессия подтверждения устарела. Начните заново из раздела «Мой доступ».")
        return

    if not code.isdigit() or len(code) != 6:
        await message.answer(
            "Введите 6 цифр из письма.\n"
            "Если хотите прервать, напишите «Отмена»."
        )
        return

    async with AsyncSessionLocal() as session:
        try:
            result = await AuthService.confirm_email_binding_code(
                db=session,
                client_id=client.id,
                email=email,
                code=code,
            )
        except ExpiredLoginCodeError as exc:
            await message.answer(str(exc))
            return
        except InvalidLoginCodeError as exc:
            await message.answer(str(exc))
            return
        except AuthError as exc:
            await message.answer(str(exc))
            return

    await state.clear()

    updated_client = await get_client_by_telegram_id(str(message.from_user.id))
    if updated_client is None:
        await message.answer("Email подтвержден, но профиль не найден. Нажмите /start")
        return

    if result.merged:
        await message.answer(
            "Email подтвержден. Аккаунт Telegram объединен с существующим аккаунтом приложения.",
            reply_markup=build_reply_keyboard_for_client(updated_client, message.from_user.id),
        )
    else:
        await message.answer(
            "Email подтвержден и привязан к вашему аккаунту.",
            reply_markup=build_reply_keyboard_for_client(updated_client, message.from_user.id),
        )

    await send_access_message(message, updated_client)


@router.message(Command("profile"))
@router.message(Command("subscription"))
@router.message(F.text == "Мой доступ")
@router.message(F.text == "Мой профиль")
@router.message(F.text == "Моя подписка")
async def cmd_access(message: Message):
    client = await get_client_by_telegram_id(str(message.from_user.id))

    if client is None:
        await message.answer("Профиль пока не найден. Нажмите /start")
        return

    await send_access_message(message, client)


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


@router.callback_query(F.data == "bind_email_start")
async def cb_bind_email_start(callback: CallbackQuery, state: FSMContext):
    client = await get_client_by_telegram_id(str(callback.from_user.id))

    if client is None:
        await callback.message.answer("Профиль пока не найден. Нажмите /start")
        await callback.answer()
        return

    await state.clear()
    await state.set_state(EmailBindingStates.waiting_for_email)

    current_email = client.email or "не привязан"
    await callback.message.answer(
        "<b>Привязка email</b>\n\n"
        f"Текущий email: <b>{current_email}</b>\n\n"
        "Введите email, который хотите привязать к аккаунту.\n"
        "После этого я отправлю код подтверждения на почту.\n\n"
        "Чтобы отменить, напишите «Отмена».",
    )
    await callback.answer()


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
        reply_markup=build_reply_keyboard_for_client(client, callback.from_user.id),
    )
    await callback.answer("Устройство отключено")


@router.callback_query(F.data == "show_happ_subscription")
async def cb_show_happ_subscription(callback: CallbackQuery):
    client = await get_client_by_telegram_id(str(callback.from_user.id))

    if client is None or not client.happ_subscription_url:
        await callback.message.answer("Ссылка для Happ пока не подготовлена.")
        await callback.answer()
        return

    happ_link = build_happ_import_url(client.happ_subscription_url) or client.happ_subscription_url

    await callback.message.answer(
        "Ссылка для подключения в Happ:\n\n"
        f"<code>{happ_link}</code>\n\n"
        "Откройте Happ и импортируйте эту ссылку как подписку.",
        parse_mode="HTML",
        reply_markup=build_reply_keyboard_for_client(client, callback.from_user.id),
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
        reply_markup=build_reply_keyboard_for_client(client, callback.from_user.id),
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

    photo = BufferedInputFile(buffer.getvalue(), filename="access_qr.png")

    await callback.message.answer_photo(
        photo,
        caption="QR-код для подключения.",
        reply_markup=build_reply_keyboard_for_client(client, callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(F.data == "open_payment_menu")
async def cb_open_payment_menu(callback: CallbackQuery):
    await callback.message.answer(
        "<b>Тарифы Freeth</b>\n\n"
        "Выберите подходящий вариант доступа:\n"
        f"• 1 месяц — {PRICE_1_MONTH}\n"
        f"• 3 месяца — {PRICE_3_MONTHS}\n"
        f"• 12 месяцев — {PRICE_12_MONTHS}\n\n"
        "Для новых пользователей также доступен пробный период на 7 дней.",
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


@router.callback_query(F.data == "open_instructions_from_access")
async def cb_open_instructions_from_access(callback: CallbackQuery):
    await callback.message.answer(
        "<b>Как подключить Freeth</b>\n\n"
        "Выберите ваше устройство. Я покажу, что скачать и как добавить доступ.",
        reply_markup=instructions_keyboard(),
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


async def activate_trial_and_respond(message: Message):
    ok, text = await activate_trial_subscription(str(message.from_user.id), days=7)

    client = await get_client_by_telegram_id(str(message.from_user.id))

    if not ok:
        await message.answer(
            text,
            reply_markup=build_reply_keyboard_for_client(client, message.from_user.id),
        )
        return

    await message.answer(
        "<b>Пробный доступ активирован на 7 дней.</b>\n\n"
        "Теперь:\n"
        "1. Скачайте приложение для своего устройства\n"
        "2. Подключите доступ\n"
        "3. Проверьте, что все работает\n\n"
        "Ниже — самые быстрые действия для старта.",
        reply_markup=build_reply_keyboard_for_client(client, message.from_user.id),
    )

    if client and (client.subscription_link or client.happ_subscription_url):
        await message.answer(
            "Доступ подготовлен. Выберите удобный способ подключения.",
            reply_markup=trial_onboarding_keyboard(client),
        )



@router.message(Command("referral"))
@router.message(Command("referrals"))
@router.message(F.text == "Пригласить друга")
async def referral_program(message: Message, bot: Bot):
    client = await get_client_by_telegram_id(str(message.from_user.id))

    if client is None:
        await message.answer("Профиль пока не найден. Нажмите /start")
        return

    if not getattr(client, "referral_code", None):
        await message.answer(
            "Реферальная ссылка пока не готова. Попробуйте снова через несколько секунд."
        )
        return

    invited_count, rewarded_count, recent_referrals = await get_referral_stats(client.id)

    me = await bot.get_me()
    referral_link = build_referral_link(me.username, client.referral_code)

    await message.answer(
        format_referral_program_text(
            referral_link=referral_link,
            invited_count=invited_count,
            rewarded_count=rewarded_count,
            bonus_days_total=getattr(client, "referral_bonus_days_total", 0) or 0,
            recent_referrals=recent_referrals,
        ),
        parse_mode="HTML",
        reply_markup=referral_share_keyboard(),
    )


@router.message(F.text == "Попробовать 7 дней")
async def trial_period(message: Message):
    await activate_trial_and_respond(message)


@router.callback_query(F.data == "activate_trial")
async def cb_activate_trial(callback: CallbackQuery):
    message = callback.message
    ok, text = await activate_trial_subscription(str(callback.from_user.id), days=7)

    client = await get_client_by_telegram_id(str(callback.from_user.id))

    if not ok:
        await message.answer(
            text,
            reply_markup=build_reply_keyboard_for_client(client, callback.from_user.id),
        )
        await callback.answer()
        return

    await message.answer(
        "<b>Пробный доступ активирован на 7 дней.</b>\n\n"
        "Теперь:\n"
        "1. Скачайте приложение для своего устройства\n"
        "2. Подключите доступ\n"
        "3. Проверьте, что все работает\n\n"
        "Ниже — самые быстрые действия для старта.",
        reply_markup=build_reply_keyboard_for_client(client, callback.from_user.id),
    )

    if client and (client.subscription_link or client.happ_subscription_url):
        await message.answer(
            "Доступ подготовлен. Выберите удобный способ подключения.",
            reply_markup=trial_onboarding_keyboard(client),
        )

    await callback.answer()


@router.message(F.text == "Оплата")
@router.message(F.text == "Тарифы")
@router.message(F.text == "Продлить доступ")
async def payment_menu(message: Message):
    await message.answer(
        "<b>Тарифы Freeth</b>\n\n"
        "Выберите подходящий вариант доступа:\n"
        f"• 1 месяц — {PRICE_1_MONTH}\n"
        f"• 3 месяца — {PRICE_3_MONTHS}\n"
        f"• 12 месяцев — {PRICE_12_MONTHS}\n\n"
        "Для новых пользователей также доступен пробный период на 7 дней.",
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
            client.paid_until.strftime("%Y-%m-%d %H:%M") if client.paid_until else "Не указано"
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
            client.paid_until.strftime("%Y-%m-%d %H:%M") if client.paid_until else "Не указано"
        )
        await message.answer(
            f"Напоминание для {client.full_name or 'Без имени'}:\n\n"
            f"Доступ истекает: {paid_until}",
            reply_markup=renewal_keyboard(),
        )


@router.message(F.text == "Помощь")
async def help_message(message: Message):
    if message.from_user.id in ADMIN_IDS:
        await message.answer(
            "Доступные действия:\n"
            "• Мой доступ\n"
            "• Как подключить\n"
            "• Попробовать 7 дней / Продлить доступ\n"
            "• Пригласить друга\n"
            "• Поддержка\n\n"
            "В разделе «Мой доступ» доступны:\n"
            "• Подключить в Happ\n"
            "• Показать данные для подключения\n"
            "• Показать QR-код\n"
            "• Войти в приложение\n"
            "• Мои устройства\n"
            "• Привязать или изменить email\n"
            "• Продлить доступ\n\n"
            f"Раздел <b>«Пригласить друга»</b> даёт вашу ссылку и кнопку отправки другу. За первую успешную оплату друга вы получите <b>+{REFERRAL_BONUS_DAYS} дней</b>.\n\n"
            "Команды администратора:\n"
            "• /admin — открыть админ-меню\n"
            "• /find [telegram_id | id | имя] — найти клиента\n"
            "• /export_clients — выгрузить клиентов в CSV\n"
            "• /news — создать новость и сделать рассылку\n"
            "• /check_expiring — показать подписки, истекающие в ближайшие 3 дня\n"
            "• /preview_expiring — посмотреть, как выглядит напоминание о продлении",
            reply_markup=build_reply_keyboard_for_client(
                await get_client_by_telegram_id(str(message.from_user.id)),
                message.from_user.id,
            ),
        )
    else:
        await message.answer(
            "Доступные действия:\n"
            "• Мой доступ\n"
            "• Как подключить\n"
            "• Попробовать 7 дней / Продлить доступ\n"
            "• Пригласить друга\n"
            "• Поддержка\n\n"
            "В разделе «Мой доступ» доступны:\n"
            "• Подключить в Happ\n"
            "• Показать данные для подключения\n"
            "• Показать QR-код\n"
            "• Войти в приложение\n"
            "• Мои устройства\n"
            "• Привязать или изменить email\n"
            "• Продлить доступ\n\n"
            f"В разделе <b>«Пригласить друга»</b> можно сразу выбрать контакт и отправить свою ссылку. За первую успешную оплату друга вы получите <b>+{REFERRAL_BONUS_DAYS} дней</b>.",
            reply_markup=build_reply_keyboard_for_client(
                await get_client_by_telegram_id(str(message.from_user.id)),
                message.from_user.id,
            ),
        )