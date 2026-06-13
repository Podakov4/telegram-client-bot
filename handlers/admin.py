from datetime import datetime, timedelta
from io import StringIO, BytesIO
import csv
import html

import qrcode
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, or_, func

from config import ADMIN_IDS
from database.db import AsyncSessionLocal
from database.models import Client, ClientVpnAccess, SubscriptionHistory, VpnNode
from services.client_access import (
    build_hiddify_import_url,
    create_vpn_access_for_client,
    get_client_by_id,
)
from utils.notes import get_note_int as _get_note_int
from services.device_service import DeviceService
from services.payments import (
    activate_subscription_days_by_client_id,
    deactivate_subscription,
)
from services.subscriptions import (
    get_expiring_clients,
    get_expired_clients_for_notice,
    mark_expired_notice_sent,
)
from utils.happ_shared import admin_instructions_text, client_instructions_keyboard

router = Router()


class AdminGrantDaysStates(StatesGroup):
    waiting_for_days = State()


class AdminSetDeviceLimitStates(StatesGroup):
    waiting_for_limit = State()


class AdminMessageClientStates(StatesGroup):
    waiting_for_text = State()


MAX_ADMIN_GRANT_DAYS = 3650
DEFAULT_DEVICE_LIMIT = 3
MAX_DEVICE_LIMIT = 50


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def admin_dashboard_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Истекают", callback_data="admin_dashboard_expiring")
    builder.button(text="Просрочены", callback_data="admin_dashboard_expired")
    builder.button(text="На trial", callback_data="admin_dashboard_trial")
    builder.button(text="Активные", callback_data="admin_dashboard_active")
    builder.button(text="Статистика", callback_data="admin_dashboard_stats")
    builder.button(text="Напомнить истекающим", callback_data="admin_notify_expiring")
    builder.button(text="Напомнить просроченным", callback_data="admin_notify_expired")
    builder.button(text="Как искать клиента", callback_data="admin_dashboard_find_help")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def admin_client_actions_keyboard(client_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="Happ ссылка", callback_data=f"admin_happ:{client_id}")
    builder.button(text="Hiddify ссылка", callback_data=f"admin_hiddify:{client_id}")
    builder.button(text="Открытая подписка", callback_data=f"admin_plain_sub:{client_id}")
    builder.button(text="VLESS по серверам", callback_data=f"admin_vless:{client_id}")
    builder.button(text="QR", callback_data=f"admin_qr:{client_id}")
    builder.button(text="Все данные клиента", callback_data=f"admin_copy_all:{client_id}")
    builder.button(text="Все ссылки", callback_data=f"admin_all_links:{client_id}")
    builder.button(text="Отправить доступ заново", callback_data=f"admin_resend_access:{client_id}")
    builder.button(text="Отправить инструкции", callback_data=f"admin_send_instructions:{client_id}")
    builder.button(text="Написать клиенту", callback_data=f"admin_write_client:{client_id}")
    builder.button(text="Выдать дни", callback_data=f"admin_grant_days:{client_id}")
    builder.button(text="Лимит устройств", callback_data=f"admin_set_device_limit:{client_id}")
    builder.button(text="Пересоздать доступ", callback_data=f"admin_recreate:{client_id}")
    builder.button(text="История подписок", callback_data=f"admin_history:{client_id}")
    builder.button(text="Отключить", callback_data=f"admin_disable:{client_id}")
    builder.adjust(2, 2, 2, 2, 1, 1, 1, 1, 1, 1, 1)
    return builder.as_markup()


def clients_list_keyboard(clients: list[Client]):
    builder = InlineKeyboardBuilder()
    for client in clients:
        title = f"{client.full_name or 'Без имени'} | tg:{client.telegram_id}"
        builder.button(text=title[:64], callback_data=f"admin_open:{client.id}")
    builder.adjust(1)
    return builder.as_markup()


admin_search_results_keyboard = clients_list_keyboard


def renewal_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Продлить подписку", callback_data="open_payment_menu")
    builder.adjust(1)
    return builder.as_markup()


def client_access_actions_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Подключить в Happ", callback_data="show_happ_subscription")
    builder.button(text="Показать данные для подключения", callback_data="show_vless_link")
    builder.button(text="Показать QR-код", callback_data="show_vless_qr")
    builder.button(text="Войти в приложение", callback_data="open_app_login_menu")
    builder.button(text="Мои устройства", callback_data="show_my_devices")
    builder.button(text="Продлить подписку", callback_data="open_payment_menu")
    builder.adjust(1)
    return builder.as_markup()


def format_client_card(client: Client) -> str:
    active_text = "Да" if client.is_active else "Нет"
    paid_text = "Да" if client.is_paid else "Нет"
    trial_used = "Да" if client.notes and "trial_used=true" in client.notes else "Нет"

    if client.paid_until:
        paid_until_text = client.paid_until.strftime("%Y-%m-%d %H:%M")
        days_left = (client.paid_until - datetime.utcnow()).days
        days_left_text = "Истекла" if days_left < 0 else f"{days_left} дн."
    else:
        paid_until_text = "Не указано"
        days_left_text = "Не указано"

    return (
        f"Клиент:\n\n"
        f"ID в БД: {client.id}\n"
        f"Telegram ID: {client.telegram_id}\n"
        f"Имя: {client.full_name or 'Не указано'}\n"
        f"Логин: {client.login or 'Не указан'}\n"
        f"XUI email: {client.xui_email or 'Не указан'}\n"
        f"UUID: {client.xui_uuid or 'Не назначен'}\n"
        f"Активен: {active_text}\n"
        f"Оплачено: {paid_text}\n"
        f"Trial использован: {trial_used}\n"
        f"Лимит устройств: {get_client_device_limit_from_notes(client)}\n"
        f"Активно до: {paid_until_text}\n"
        f"Осталось: {days_left_text}\n"
        f"Ссылка VLESS: {'Есть' if client.subscription_link else 'Нет'}\n"
        f"Happ ссылка: {'Есть' if client.happ_subscription_url else 'Нет'}"
    )


def format_admin_client_bundle(client: Client) -> str:
    active_text = "Да" if client.is_active else "Нет"
    paid_text = "Да" if client.is_paid else "Нет"
    trial_used = "Да" if client.notes and "trial_used=true" in client.notes else "Нет"
    paid_until_text = (
        client.paid_until.strftime("%Y-%m-%d %H:%M") if client.paid_until else "Не указано"
    )

    happ_link = client.happ_subscription_url or "Не подготовлена"
    vless_link = client.subscription_link or "Не подготовлена"

    return (
        f"<b>Данные клиента для копирования</b>\n\n"
        f"ID в БД: <code>{client.id}</code>\n"
        f"Telegram ID: <code>{client.telegram_id or '—'}</code>\n"
        f"Имя: {client.full_name or 'Не указано'}\n"
        f"Логин: <code>{client.login or 'Не указан'}</code>\n"
        f"XUI email: <code>{client.xui_email or 'Не указан'}</code>\n"
        f"UUID: <code>{client.xui_uuid or 'Не назначен'}</code>\n"
        f"Активен: {active_text}\n"
        f"Оплачено: {paid_text}\n"
        f"Trial использован: {trial_used}\n"
        f"Активно до: {paid_until_text}\n\n"
        f"<b>Happ ссылка</b>\n"
        f"<code>{happ_link}</code>\n\n"
        f"<b>VLESS ссылка</b>\n"
        f"<code>{vless_link}</code>"
    )


def format_history_rows(history_rows: list[SubscriptionHistory]) -> str:
    if not history_rows:
        return "История подписок пуста."

    lines = ["История подписок:\n"]
    for row in history_rows:
        start_text = row.starts_at.strftime("%Y-%m-%d %H:%M")
        end_text = row.ends_at.strftime("%Y-%m-%d %H:%M")
        trial_text = "trial" if row.is_trial else "paid"

        lines.append(
            f"#{row.id} | {row.plan_code} | {trial_text}\n"
            f"с {start_text} до {end_text}"
        )

    return "\n\n".join(lines)



def parse_client_notes(notes: str | None) -> tuple[dict[str, str], list[str]]:
    data: dict[str, str] = {}
    raw_lines: list[str] = []

    if not notes:
        return data, raw_lines

    for line in notes.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "=" in stripped:
            key, value = stripped.split("=", 1)
            data[key.strip()] = value.strip()
        else:
            raw_lines.append(stripped)

    return data, raw_lines


def dump_client_notes(data: dict[str, str], raw_lines: list[str]) -> str | None:
    lines = [f"{key}={data[key]}" for key in sorted(data.keys())]
    lines.extend(raw_lines)
    return "\n".join(lines) if lines else None


def get_client_device_limit_from_notes(client: Client) -> int:
    return _get_note_int(client.notes, "max_devices", DEFAULT_DEVICE_LIMIT)


async def get_client_device_limit_state(client_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if not client:
            return None, None

        limit_info = await DeviceService.get_device_limit_info(
            db=session,
            client=client,
            default_max_devices=DEFAULT_DEVICE_LIMIT,
        )
        return client, limit_info


async def update_client_device_limit(client_id: int, max_devices: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if not client:
            return None, None

        data, raw_lines = parse_client_notes(client.notes)
        data["max_devices"] = str(max_devices)
        client.notes = dump_client_notes(data, raw_lines)
        client.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(client)

        limit_info = await DeviceService.get_device_limit_info(
            db=session,
            client=client,
            default_max_devices=DEFAULT_DEVICE_LIMIT,
        )
        return client, limit_info


def format_device_limit_admin_text(client: Client, limit_info) -> str:
    return (
        "<b>Лимит устройств клиента</b>\n\n"
        f"ID в БД: <code>{client.id}</code>\n"
        f"Telegram ID: <code>{client.telegram_id or '—'}</code>\n"
        f"Имя: {client.full_name or 'Не указано'}\n\n"
        f"Текущий лимит: <b>{limit_info.max_devices}</b>\n"
        f"Активных устройств: <b>{limit_info.active_devices}</b>\n\n"
        f"Введите новый лимит от <b>1</b> до <b>{MAX_DEVICE_LIMIT}</b>.\n"
        "Например: <code>3</code>, <code>5</code>, <code>10</code>.\n\n"
        "Если уменьшить лимит ниже текущего количества активных устройств, "
        "уже активные устройства не отключатся автоматически, но новые входы будут запрещены, "
        "пока клиент не отключит лишние устройства."
    )


def html_escape(value) -> str:
    if value is None:
        return "—"
    return html.escape(str(value), quote=False)


async def get_client_vpn_links_by_db_id(client_id: int) -> list[tuple[ClientVpnAccess, VpnNode]]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ClientVpnAccess, VpnNode)
            .join(VpnNode, VpnNode.id == ClientVpnAccess.node_id)
            .where(ClientVpnAccess.client_id == client_id)
            .order_by(VpnNode.sort_order.asc(), VpnNode.id.asc(), ClientVpnAccess.id.asc())
        )
        return list(result.all())


def format_plain_subscription_for_admin(client: Client) -> str:
    plain_url = client.happ_subscription_url or "Не подготовлена"

    return (
        f"<b>Открытая подписка клиента</b>\n\n"
        f"ID в БД: <code>{client.id}</code>\n"
        f"Telegram ID: <code>{html_escape(client.telegram_id)}</code>\n"
        f"Имя: {html_escape(client.full_name or 'Не указано')}\n\n"
        f"<b>Незашифрованная subscription-ссылка</b>\n"
        f"<code>{html_escape(plain_url)}</code>\n\n"
        f"Эта ссылка открывает обычный список VLESS-ссылок через "
        f"<code>/sub/token</code>."
    )


def format_server_links_for_admin(
    client: Client,
    pairs: list[tuple[ClientVpnAccess, VpnNode]],
) -> str:
    lines = [
        "<b>Отдельные VLESS-ссылки по серверам</b>",
        "",
        f"ID в БД: <code>{client.id}</code>",
        f"Telegram ID: <code>{html_escape(client.telegram_id)}</code>",
        f"Имя: {html_escape(client.full_name or 'Не указано')}",
        "",
    ]

    if not pairs:
        lines.append("Отдельные серверные ссылки не найдены.")
        return "\n".join(lines)

    for access, node in pairs:
        enabled_text = "включена" if access.is_enabled and node.is_active else "отключена"
        link = access.subscription_link or "Не подготовлена"

        lines.extend([
            f"<b>{html_escape(node.display_name or node.name)} [{html_escape(node.code)}]</b>",
            f"Домен: <code>{html_escape(node.vless_domain)}:{node.vless_public_port}</code>",
            f"Path: <code>{html_escape(node.vless_path)}</code>",
            f"SNI: <code>{html_escape(node.vless_sni)}</code>",
            f"Статус: <b>{enabled_text}</b>",
            f"<code>{html_escape(link)}</code>",
            "",
        ])

    return "\n".join(lines).strip()


def format_all_admin_links_bundle(
    client: Client,
    pairs: list[tuple[ClientVpnAccess, VpnNode]],
) -> str:
    active_text = "Да" if client.is_active else "Нет"
    paid_text = "Да" if client.is_paid else "Нет"
    paid_until_text = (
        client.paid_until.strftime("%Y-%m-%d %H:%M") if client.paid_until else "Не указано"
    )

    header = (
        f"<b>Все ссылки клиента</b>\n\n"
        f"ID в БД: <code>{client.id}</code>\n"
        f"Telegram ID: <code>{html_escape(client.telegram_id)}</code>\n"
        f"Имя: {html_escape(client.full_name or 'Не указано')}\n"
        f"Логин: <code>{html_escape(client.login or 'Не указан')}</code>\n"
        f"Активен: {active_text}\n"
        f"Оплачено: {paid_text}\n"
        f"Активно до: {html_escape(paid_until_text)}\n\n"
        f"<b>Happ / открытая подписка</b>\n"
        f"<code>{html_escape(client.happ_subscription_url or 'Не подготовлена')}</code>\n\n"
    )

    return header + format_server_links_for_admin(client, pairs)


def split_admin_text(text: str, limit: int = 3500) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks = []
    current = ""

    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block

        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current)

        if len(block) <= limit:
            current = block
        else:
            for i in range(0, len(block), limit):
                chunks.append(block[i:i + limit])
            current = ""

    if current:
        chunks.append(current)

    return chunks


async def answer_admin_text(message: Message, text: str) -> None:
    for chunk in split_admin_text(text):
        await message.answer(chunk, parse_mode="HTML")


async def send_admin_all_links(message: Message, client: Client) -> None:
    pairs = await get_client_vpn_links_by_db_id(client.id)
    text = format_all_admin_links_bundle(client, pairs)
    await answer_admin_text(message, text)


async def get_client_history(client_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SubscriptionHistory)
            .where(SubscriptionHistory.client_id == client_id)
            .order_by(SubscriptionHistory.id.desc())
            .limit(20)
        )
        return list(result.scalars().all())


async def find_clients(query: str):
    async with AsyncSessionLocal() as session:
        stmt = select(Client)

        if query.isdigit():
            stmt = stmt.where(
                or_(
                    Client.telegram_id == query,
                    Client.id == int(query),
                )
            )
        else:
            stmt = stmt.where(Client.full_name.ilike(f"%{query}%"))

        result = await session.execute(stmt.limit(10))
        return list(result.scalars().all())


async def get_active_clients(limit: int = 20):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client)
            .where(Client.is_active == True)
            .order_by(Client.paid_until.asc().nullslast())
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_trial_clients(limit: int = 20):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client)
            .where(
                Client.is_active == True,
                Client.is_paid == False,
                Client.notes.is_not(None),
            )
            .order_by(Client.paid_until.asc().nullslast())
            .limit(limit)
        )
        clients = list(result.scalars().all())
        return [c for c in clients if c.notes and "trial_used=true" in c.notes]



async def get_expired_clients_all(limit: int = 20):
    now = datetime.utcnow()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client)
            .where(
                Client.paid_until.is_not(None),
                Client.paid_until <= now,
            )
            .order_by(Client.paid_until.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def send_access_again_to_client(bot: Bot, client: Client) -> tuple[bool, str]:
    if not client.telegram_id:
        return False, "У клиента не указан Telegram ID."

    if not client.subscription_link and not client.happ_subscription_url:
        return False, "У клиента пока нет подготовленного доступа."

    name = client.full_name or "пользователь"

    text = (
        f"Здравствуйте, {name}!\n\n"
        "Мы отправили ваш доступ Freeth заново.\n\n"
        "Выберите удобный вариант ниже:\n"
        "• подключить в Happ\n"
        "• посмотреть данные для подключения\n"
        "• получить QR-код\n"
        "• войти в приложение"
    )

    try:
        await bot.send_message(
            chat_id=int(client.telegram_id),
            text=text,
            reply_markup=client_access_actions_keyboard(),
        )
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


async def send_instructions_to_client(bot: Bot, client: Client) -> tuple[bool, str]:
    if not client.telegram_id:
        return False, "У клиента не указан Telegram ID."

    name = client.full_name or "пользователь"

    text = admin_instructions_text(name)

    try:
        await bot.send_message(
            chat_id=int(client.telegram_id),
            text=text,
            reply_markup=client_instructions_keyboard(),
        )
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


async def send_custom_message_to_client(
    bot: Bot,
    client: Client,
    admin_text: str,
) -> tuple[bool, str]:
    if not client.telegram_id:
        return False, "У клиента не указан Telegram ID."

    text = (
        "Сообщение от Freeth:\n\n"
        f"{admin_text.strip()}"
    )

    try:
        await bot.send_message(
            chat_id=int(client.telegram_id),
            text=text,
        )
        return True, "ok"
    except Exception as exc:
        return False, format_telegram_send_error(exc)


async def send_expiring_notice(bot: Bot, client: Client) -> bool:
    try:
        paid_until = client.paid_until.strftime("%Y-%m-%d %H:%M") if client.paid_until else "скоро"
        text = (
            f"Здравствуйте, {client.full_name or 'пользователь'}!\n\n"
            f"Ваша подписка истекает: {paid_until}\n\n"
            "Чтобы не потерять доступ, продлите подписку заранее."
        )

        await bot.send_message(
            chat_id=int(client.telegram_id),
            text=text,
            reply_markup=renewal_keyboard(),
        )
        return True
    except Exception:
        return False


def format_telegram_send_error(exc: Exception) -> str:
    error_type = type(exc).__name__
    error_text = str(exc)
    normalized = error_text.lower()

    if "bot was blocked by the user" in normalized:
        return "пользователь заблокировал бота"

    if "chat not found" in normalized:
        return "чат не найден: пользователь не запускал бота или Telegram ID неверный"

    if "user is deactivated" in normalized:
        return "аккаунт Telegram деактивирован"

    if "forbidden" in normalized:
        return f"Telegram запретил отправку: {error_text}"

    if "bad request" in normalized:
        return f"ошибка Telegram-запроса: {error_text}"

    return f"{error_type}: {error_text}"


async def send_expired_notice(bot: Bot, client: Client) -> tuple[bool, str]:
    try:
        text = (
            f"Здравствуйте, {client.full_name or 'пользователь'}!\n\n"
            "Срок действия вашей подписки истек.\n\n"
            "Чтобы восстановить доступ, продлите подписку."
        )

        await bot.send_message(
            chat_id=int(client.telegram_id),
            text=text,
            reply_markup=renewal_keyboard(),
        )
        return True, "ok"
    except Exception as exc:
        return False, format_telegram_send_error(exc)


async def get_admin_stats():
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    async with AsyncSessionLocal() as session:
        total_clients = await session.scalar(select(func.count()).select_from(Client))

        active_clients = await session.scalar(
            select(func.count()).select_from(Client).where(Client.is_active == True)
        )

        trial_clients = await session.scalar(
            select(func.count()).select_from(Client).where(
                Client.is_active == True,
                Client.is_paid == False,
                Client.notes.is_not(None),
            )
        )

        expiring_clients = await session.scalar(
            select(func.count()).select_from(Client).where(
                Client.is_active == True,
                Client.paid_until.is_not(None),
                Client.paid_until > now,
                Client.paid_until <= now + timedelta(days=3),
            )
        )

        expired_clients = await session.scalar(
            select(func.count()).select_from(Client).where(
                Client.paid_until.is_not(None),
                Client.paid_until <= now,
            )
        )

        activations_today = await session.scalar(
            select(func.count()).select_from(SubscriptionHistory).where(
                SubscriptionHistory.created_at >= today_start
            )
        )

        activations_week = await session.scalar(
            select(func.count()).select_from(SubscriptionHistory).where(
                SubscriptionHistory.created_at >= week_start
            )
        )

        activations_month = await session.scalar(
            select(func.count()).select_from(SubscriptionHistory).where(
                SubscriptionHistory.created_at >= month_start
            )
        )

    return {
        "total_clients": total_clients or 0,
        "active_clients": active_clients or 0,
        "trial_clients": trial_clients or 0,
        "expiring_clients": expiring_clients or 0,
        "expired_clients": expired_clients or 0,
        "activations_today": activations_today or 0,
        "activations_week": activations_week or 0,
        "activations_month": activations_month or 0,
    }


@router.message(Command("admin"))
@router.message(F.text.regexp(r"(?i)^админ$"))
async def admin_menu(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Недостаточно прав.")
        return

    await message.answer("Админ-дашборд:", reply_markup=admin_dashboard_keyboard())


@router.message(Command("find"))
async def cmd_find(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Недостаточно прав.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /find [telegram_id | id | имя]")
        return

    query = parts[1].strip()
    clients = await find_clients(query)

    if not clients:
        await message.answer("Клиенты не найдены.")
        return

    if len(clients) == 1:
        client = clients[0]
        await message.answer(
            format_client_card(client),
            reply_markup=admin_client_actions_keyboard(client.id),
        )
        return

    await message.answer(
        f"Найдено клиентов: {len(clients)}. Выберите нужного:",
        reply_markup=admin_search_results_keyboard(clients),
    )



@router.message(Command("admin_links"))
async def cmd_admin_links(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Недостаточно прав.")
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "Использование:\n\n"
            "<code>/admin_links telegram_id</code>\n"
            "<code>/admin_links client_id</code>\n"
            "<code>/admin_links имя</code>\n\n"
            "Пример:\n"
            "<code>/admin_links 766928002</code>"
        )
        return

    query = parts[1].strip()
    clients = await find_clients(query)

    if not clients:
        await message.answer("Клиенты не найдены.")
        return

    if len(clients) > 1:
        await message.answer(
            f"Найдено клиентов: {len(clients)}. Выберите нужного:",
            reply_markup=admin_search_results_keyboard(clients),
        )
        return

    await send_admin_all_links(message, clients[0])


@router.message(Command("set_devices"))
async def cmd_set_devices(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Недостаточно прав.")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "Использование:\n\n"
            "<code>/set_devices telegram_id лимит</code>\n"
            "<code>/set_devices client_id лимит</code>\n\n"
            "Пример:\n"
            "<code>/set_devices 766928002 3</code>"
        )
        return

    query = parts[1].strip()
    raw_limit = parts[2].strip()

    if not raw_limit.isdigit():
        await message.answer("Лимит должен быть целым числом.")
        return

    new_limit = int(raw_limit)
    if new_limit <= 0 or new_limit > MAX_DEVICE_LIMIT:
        await message.answer(f"Введите лимит от 1 до {MAX_DEVICE_LIMIT}.")
        return

    clients = await find_clients(query)
    if not clients:
        await message.answer("Клиенты не найдены.")
        return

    if len(clients) > 1:
        await message.answer(
            f"Найдено клиентов: {len(clients)}. Выберите нужного:",
            reply_markup=admin_search_results_keyboard(clients),
        )
        return

    client, limit_info = await update_client_device_limit(clients[0].id, new_limit)
    if not client:
        await message.answer("Клиент не найден.")
        return

    await message.answer(
        "Лимит устройств обновлен.\n\n"
        f"Клиент: <b>{client.full_name or 'Без имени'}</b>\n"
        f"ID: <code>{client.id}</code>\n"
        f"Активных устройств: <b>{limit_info.active_devices}</b>\n"
        f"Новый лимит: <b>{limit_info.max_devices}</b>",
        parse_mode="HTML",
        reply_markup=admin_client_actions_keyboard(client.id),
    )


@router.message(AdminGrantDaysStates.waiting_for_days)
async def process_admin_grant_days(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("Недостаточно прав.")
        return

    raw_text = (message.text or "").strip()
    if raw_text.lower() in {"отмена", "/cancel", "cancel"}:
        await state.clear()
        await message.answer("Выдача дней отменена.")
        return

    if not raw_text.isdigit():
        await message.answer(
            "Введите целое количество дней, например <code>20</code> или <code>45</code>.\n"
            "Чтобы отменить, напишите <b>Отмена</b>."
        )
        return

    days = int(raw_text)
    if days <= 0 or days > MAX_ADMIN_GRANT_DAYS:
        await message.answer(
            f"Введите число от 1 до {MAX_ADMIN_GRANT_DAYS}.\n"
            "Чтобы отменить, напишите <b>Отмена</b>."
        )
        return

    data = await state.get_data()
    client_id = data.get("admin_grant_client_id")
    if not client_id:
        await state.clear()
        await message.answer("Сессия выдачи дней устарела. Откройте клиента заново.")
        return

    ok = await activate_subscription_days_by_client_id(
        client_id=int(client_id),
        days=days,
        reason=f"admin manual extension by user_id={message.from_user.id}",
        plan_code=f"admin_{days}d",
        mark_paid=True,
    )
    await state.clear()

    if not ok:
        await message.answer("Не удалось выдать доступ на указанное количество дней.")
        return

    updated = await get_client_by_id(int(client_id))
    await message.answer(
        f"Доступ выдан на <b>{days}</b> дн.\n\n{format_client_card(updated)}",
        reply_markup=admin_client_actions_keyboard(updated.id),
    )


@router.message(AdminSetDeviceLimitStates.waiting_for_limit)
async def process_admin_set_device_limit(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("Недостаточно прав.")
        return

    raw_text = (message.text or "").strip()
    if raw_text.lower() in {"отмена", "/cancel", "cancel"}:
        await state.clear()
        await message.answer("Изменение лимита устройств отменено.")
        return

    if not raw_text.isdigit():
        await message.answer(
            f"Введите целое число от 1 до {MAX_DEVICE_LIMIT}.\n"
            "Чтобы отменить, напишите <b>Отмена</b>.",
            parse_mode="HTML",
        )
        return

    new_limit = int(raw_text)
    if new_limit <= 0 or new_limit > MAX_DEVICE_LIMIT:
        await message.answer(
            f"Введите число от 1 до {MAX_DEVICE_LIMIT}.\n"
            "Чтобы отменить, напишите <b>Отмена</b>.",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    client_id = data.get("admin_device_limit_client_id")
    if not client_id:
        await state.clear()
        await message.answer("Сессия изменения лимита устарела. Откройте клиента заново.")
        return

    client, limit_info = await update_client_device_limit(int(client_id), new_limit)
    await state.clear()

    if not client:
        await message.answer("Клиент не найден.")
        return

    await message.answer(
        "Лимит устройств обновлен.\n\n"
        f"Клиент: <b>{client.full_name or 'Без имени'}</b>\n"
        f"ID: <code>{client.id}</code>\n"
        f"Активных устройств: <b>{limit_info.active_devices}</b>\n"
        f"Новый лимит: <b>{limit_info.max_devices}</b>",
        parse_mode="HTML",
        reply_markup=admin_client_actions_keyboard(client.id),
    )


@router.message(AdminMessageClientStates.waiting_for_text)
async def process_admin_message_to_client(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("Недостаточно прав.")
        return

    raw_text = (message.text or "").strip()

    if raw_text.lower() in {"отмена", "/cancel", "cancel"}:
        await state.clear()
        await message.answer("Отправка сообщения клиенту отменена.")
        return

    if not raw_text:
        await message.answer(
            "Введите текст сообщения для клиента.\n"
            "Чтобы отменить, напишите <b>Отмена</b>."
        )
        return

    if len(raw_text) > 3500:
        await message.answer(
            "Сообщение слишком длинное. Сократите текст до 3500 символов.\n"
            "Чтобы отменить, напишите <b>Отмена</b>."
        )
        return

    data = await state.get_data()
    client_id = data.get("admin_message_client_id")

    if not client_id:
        await state.clear()
        await message.answer("Сессия отправки сообщения устарела. Откройте клиента заново.")
        return

    client = await get_client_by_id(int(client_id))
    if client is None:
        await state.clear()
        await message.answer("Клиент не найден.")
        return

    ok, details = await send_custom_message_to_client(
        bot=bot,
        client=client,
        admin_text=raw_text,
    )

    await state.clear()

    if not ok:
        await message.answer(
            "Не удалось отправить сообщение клиенту.\n\n"
            f"Клиент: <b>{html_escape(client.full_name or 'Без имени')}</b>\n"
            f"ID: <code>{client.id}</code>\n"
            f"TG: <code>{html_escape(client.telegram_id or '—')}</code>\n"
            f"Причина: {html_escape(details)}",
            reply_markup=admin_client_actions_keyboard(client.id),
        )
        return

    await message.answer(
        "Сообщение отправлено клиенту.\n\n"
        f"Клиент: <b>{html_escape(client.full_name or 'Без имени')}</b>\n"
        f"ID: <code>{client.id}</code>\n"
        f"TG: <code>{html_escape(client.telegram_id or '—')}</code>",
        reply_markup=admin_client_actions_keyboard(client.id),
    )


@router.callback_query(F.data == "admin_dashboard_find_help")
async def cb_admin_dashboard_find_help(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    await callback.message.answer(
        "Поиск клиента:\n\n"
        "• <code>/find [telegram_id | id | имя]</code>\n"
        "• <code>/find 766928002</code>\n"
        "• <code>/find 1</code>\n"
        "• <code>/find Константин</code>"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_dashboard_expiring")
async def cb_admin_dashboard_expiring(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    clients = await get_expiring_clients(days=3)

    if not clients:
        await callback.message.answer("Нет подписок, истекающих в ближайшие 3 дня.")
        await callback.answer()
        return

    await callback.message.answer(
        f"Истекают в ближайшие 3 дня: {len(clients)}",
        reply_markup=clients_list_keyboard(clients[:20]),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_dashboard_expired")
async def cb_admin_dashboard_expired(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    clients = await get_expired_clients_all(limit=20)

    if not clients:
        await callback.message.answer("Нет просроченных подписок.")
        await callback.answer()
        return

    await callback.message.answer(
        f"Просроченные подписки: {len(clients)}",
        reply_markup=clients_list_keyboard(clients),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_dashboard_active")
async def cb_admin_dashboard_active(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    clients = await get_active_clients(limit=20)

    if not clients:
        await callback.message.answer("Нет активных клиентов.")
        await callback.answer()
        return

    await callback.message.answer(
        f"Активные клиенты: {len(clients)}",
        reply_markup=clients_list_keyboard(clients),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_dashboard_trial")
async def cb_admin_dashboard_trial(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    clients = await get_trial_clients(limit=20)

    if not clients:
        await callback.message.answer("Нет клиентов на trial.")
        await callback.answer()
        return

    await callback.message.answer(
        f"Клиенты на trial: {len(clients)}",
        reply_markup=clients_list_keyboard(clients),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_notify_expiring")
async def cb_admin_notify_expiring(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    clients = await get_expiring_clients(days=3)

    if not clients:
        await callback.message.answer("Нет клиентов для напоминания об истечении.")
        await callback.answer()
        return

    sent = 0
    failed = 0

    for client in clients:
        ok = await send_expiring_notice(bot, client)
        if ok:
            sent += 1
        else:
            failed += 1

    await callback.message.answer(
        f"Готово.\n\nНапоминаний отправлено: {sent}\nОшибок: {failed}"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_notify_expired")
async def cb_admin_notify_expired(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    clients = await get_expired_clients_for_notice(cooldown_hours=20)

    if not clients:
        await callback.message.answer(
            "Нет клиентов для напоминания о просрочке.\n\n"
            "Возможные причины:\n"
            "• просроченных нет;\n"
            "• всем уже отправляли напоминание за последние 20 часов;\n"
            "• у клиентов нет Telegram ID."
        )
        await callback.answer()
        return

    sent = 0
    failed = 0
    skipped = 0
    sent_rows: list[str] = []
    failed_rows: list[str] = []
    skipped_rows: list[str] = []

    for client in clients:
        client_label = (
            f"ID={client.id} | tg={client.telegram_id or '—'} | "
            f"{client.full_name or 'Без имени'}"
        )

        if not client.telegram_id:
            skipped += 1
            skipped_rows.append(f"• {client_label} — нет Telegram ID")
            continue

        ok, details = await send_expired_notice(bot, client)

        if ok:
            sent += 1
            sent_rows.append(f"• {client_label}")
            await mark_expired_notice_sent(client.id)
        else:
            failed += 1
            failed_rows.append(f"• {client_label} — {details}")

    lines = [
        "Готово.",
        "",
        f"Сообщений отправлено: {sent}",
        f"Ошибок: {failed}",
        f"Пропущено без Telegram ID: {skipped}",
    ]

    if sent_rows:
        lines.extend(["", "Отправлено:", *sent_rows[:20]])

    if failed_rows:
        lines.extend(["", "Ошибки:", *failed_rows[:20]])

    if skipped_rows:
        lines.extend(["", "Пропущено:", *skipped_rows[:20]])

    text = "\n".join(lines)

    for chunk in split_admin_text(text, limit=3500):
        await callback.message.answer(chunk)

    await callback.answer()


@router.callback_query(F.data.startswith("admin_open:"))
async def cb_admin_open(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":")[1])
    client = await get_client_by_id(client_id)

    if not client:
        await callback.message.answer("Клиент не найден.")
        await callback.answer()
        return

    await callback.message.answer(
        format_client_card(client),
        reply_markup=admin_client_actions_keyboard(client.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_history:"))
async def cb_admin_history(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":")[1])
    client = await get_client_by_id(client_id)

    if not client:
        await callback.message.answer("Клиент не найден.")
        await callback.answer()
        return

    history_rows = await get_client_history(client_id)

    await callback.message.answer(
        f"{client.full_name or 'Без имени'}\n\n{format_history_rows(history_rows)}",
        reply_markup=admin_client_actions_keyboard(client.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_happ:"))
async def cb_admin_happ(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":", 1)[1])
    client = await get_client_by_id(client_id)

    if client is None or not client.happ_subscription_url:
        await callback.message.answer("Happ ссылка не найдена.")
        await callback.answer()
        return

    await callback.message.answer(
        f"<b>{client.full_name or 'Без имени'}</b>\n"
        f"ID: <code>{client.id}</code>\n"
        f"TG: <code>{client.telegram_id or '—'}</code>\n\n"
        f"<code>{client.happ_subscription_url}</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hiddify:"))
async def cb_admin_hiddify(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":", 1)[1])
    client = await get_client_by_id(client_id)

    if client is None or not client.happ_subscription_url:
        await callback.message.answer("Hiddify ссылка не найдена.")
        await callback.answer()
        return

    hiddify_link = build_hiddify_import_url(client.happ_subscription_url) or client.happ_subscription_url

    await callback.message.answer(
        f"<b>{client.full_name or 'Без имени'}</b>\n"
        f"ID: <code>{client.id}</code>\n"
        f"TG: <code>{client.telegram_id or '—'}</code>\n\n"
        f"<b>Hiddify ссылка:</b>\n"
        f"<code>{hiddify_link}</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_plain_sub:"))
async def cb_admin_plain_sub(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":", 1)[1])
    client = await get_client_by_id(client_id)

    if client is None:
        await callback.message.answer("Клиент не найден.")
        await callback.answer()
        return

    await callback.message.answer(
        format_plain_subscription_for_admin(client),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_all_links:"))
async def cb_admin_all_links(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":", 1)[1])
    client = await get_client_by_id(client_id)

    if client is None:
        await callback.message.answer("Клиент не найден.")
        await callback.answer()
        return

    pairs = await get_client_vpn_links_by_db_id(client.id)
    text = format_all_admin_links_bundle(client, pairs)

    for chunk in split_admin_text(text):
        await callback.message.answer(chunk, parse_mode="HTML")

    await callback.answer("Готово")


@router.callback_query(F.data.startswith("admin_vless:"))
async def cb_admin_vless(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":", 1)[1])
    client = await get_client_by_id(client_id)

    if client is None:
        await callback.message.answer("Клиент не найден.")
        await callback.answer()
        return

    pairs = await get_client_vpn_links_by_db_id(client.id)
    text = format_server_links_for_admin(client, pairs)

    for chunk in split_admin_text(text):
        await callback.message.answer(chunk, parse_mode="HTML")

    await callback.answer()


@router.callback_query(F.data.startswith("admin_qr:"))
async def cb_admin_qr(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":", 1)[1])
    client = await get_client_by_id(client_id)

    if client is None or not client.subscription_link:
        await callback.message.answer("Ссылка подключения не найдена.")
        await callback.answer()
        return

    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(client.subscription_link)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    photo = BufferedInputFile(buffer.getvalue(), filename=f"client_{client.id}_qr.png")

    await callback.message.answer_photo(
        photo,
        caption=(
            f"QR клиента: <b>{client.full_name or 'Без имени'}</b>\n"
            f"ID: <code>{client.id}</code>"
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_copy_all:"))
async def cb_admin_copy_all(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":", 1)[1])
    client = await get_client_by_id(client_id)

    if client is None:
        await callback.message.answer("Клиент не найден.")
        await callback.answer()
        return

    await callback.message.answer(
        format_admin_client_bundle(client),
        parse_mode="HTML",
    )
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("admin_resend_access:"))
async def cb_admin_resend_access(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":", 1)[1])
    client = await get_client_by_id(client_id)

    if client is None:
        await callback.message.answer("Клиент не найден.")
        await callback.answer()
        return

    ok, details = await send_access_again_to_client(bot, client)
    if not ok:
        await callback.message.answer(
            f"Не удалось отправить доступ заново.\n\nПричина: {details}"
        )
        await callback.answer()
        return

    await callback.message.answer(
        f"Клиенту отправлен доступ заново: {client.full_name or 'Без имени'} "
        f"(ID {client.id})."
    )
    await callback.answer("Отправлено")


@router.callback_query(F.data.startswith("admin_send_instructions:"))
async def cb_admin_send_instructions(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":", 1)[1])
    client = await get_client_by_id(client_id)

    if client is None:
        await callback.message.answer("Клиент не найден.")
        await callback.answer()
        return

    ok, details = await send_instructions_to_client(bot, client)
    if not ok:
        await callback.message.answer(
            f"Не удалось отправить инструкции.\n\nПричина: {details}"
        )
        await callback.answer()
        return

    await callback.message.answer(
        f"Клиенту отправлены инструкции: {client.full_name or 'Без имени'} "
        f"(ID {client.id})."
    )
    await callback.answer("Отправлено")


@router.callback_query(F.data.startswith("admin_set_device_limit:"))
async def cb_admin_set_device_limit(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":", 1)[1])
    client, limit_info = await get_client_device_limit_state(client_id)

    if not client:
        await callback.message.answer("Клиент не найден.")
        await callback.answer()
        return

    await state.clear()
    await state.set_state(AdminSetDeviceLimitStates.waiting_for_limit)
    await state.update_data(admin_device_limit_client_id=client.id)

    await callback.message.answer(
        format_device_limit_admin_text(client, limit_info),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_write_client:"))
async def cb_admin_write_client(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":", 1)[1])
    client = await get_client_by_id(client_id)

    if client is None:
        await callback.message.answer("Клиент не найден.")
        await callback.answer()
        return

    if not client.telegram_id:
        await callback.message.answer(
            "У клиента не указан Telegram ID, отправить сообщение нельзя.",
            reply_markup=admin_client_actions_keyboard(client.id),
        )
        await callback.answer()
        return

    await state.clear()
    await state.set_state(AdminMessageClientStates.waiting_for_text)
    await state.update_data(admin_message_client_id=client.id)

    await callback.message.answer(
        "<b>Сообщение клиенту от имени бота</b>\n\n"
        f"Клиент: <b>{html_escape(client.full_name or 'Без имени')}</b>\n"
        f"ID: <code>{client.id}</code>\n"
        f"TG: <code>{html_escape(client.telegram_id)}</code>\n\n"
        "Напишите текст сообщения следующим сообщением.\n\n"
        "Клиент получит его так:\n"
        "<code>Сообщение от Freeth:</code>\n"
        "<code>ваш текст</code>\n\n"
        "Чтобы отменить, напишите <b>Отмена</b>."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_grant_days:"))
async def cb_admin_grant_days(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":", 1)[1])
    client = await get_client_by_id(client_id)
    if not client:
        await callback.message.answer("Клиент не найден.")
        await callback.answer()
        return

    await state.clear()
    await state.set_state(AdminGrantDaysStates.waiting_for_days)
    await state.update_data(admin_grant_client_id=client.id)

    await callback.message.answer(
        "<b>Выдача доступа в днях</b>\n\n"
        f"Клиент: <b>{client.full_name or 'Без имени'}</b>\n"
        f"ID: <code>{client.id}</code>\n\n"
        "Введите количество дней, которое нужно выдать.\n"
        f"Допустимый диапазон: <b>1–{MAX_ADMIN_GRANT_DAYS}</b>.\n\n"
        "Например: <code>20</code>\n"
        "Чтобы отменить, напишите <b>Отмена</b>."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_recreate:"))
async def cb_admin_recreate(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":")[1])
    client = await get_client_by_id(client_id)
    if not client:
        await callback.message.answer("Клиент не найден.")
        await callback.answer()
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Client).where(Client.id == client_id))
        db_client = result.scalar_one_or_none()
        if db_client:
            db_client.xui_uuid = None
            db_client.subscription_link = None
            db_client.happ_subscription_url = None
            db_client.xui_email = None
            db_client.login = None
            db_client.updated_at = datetime.utcnow()
            await session.commit()

    ok = await create_vpn_access_for_client(client.telegram_id)
    if not ok:
        await callback.message.answer("Не удалось пересоздать доступ.")
        await callback.answer()
        return

    updated = await get_client_by_id(client_id)
    await callback.message.answer(
        f"Доступ пересоздан.\n\n{format_client_card(updated)}",
        reply_markup=admin_client_actions_keyboard(updated.id),
    )
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("admin_disable:"))
async def cb_admin_disable(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":")[1])
    client = await get_client_by_id(client_id)
    if not client:
        await callback.message.answer("Клиент не найден.")
        await callback.answer()
        return

    ok = await deactivate_subscription(client.telegram_id)
    if not ok:
        await callback.message.answer("Не удалось отключить подписку.")
        await callback.answer()
        return

    updated = await get_client_by_id(client_id)
    await callback.message.answer(
        f"Подписка отключена.\n\n{format_client_card(updated)}",
        reply_markup=admin_client_actions_keyboard(updated.id),
    )
    await callback.answer("Готово")


@router.callback_query(F.data == "admin_dashboard_stats")
async def cb_admin_dashboard_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    stats = await get_admin_stats()

    await callback.message.answer(
        "Статистика:\n\n"
        f"Всего клиентов: {stats['total_clients']}\n"
        f"Активных: {stats['active_clients']}\n"
        f"На trial: {stats['trial_clients']}\n"
        f"Истекают за 3 дня: {stats['expiring_clients']}\n"
        f"Просрочены: {stats['expired_clients']}\n\n"
        f"Активаций сегодня: {stats['activations_today']}\n"
        f"Активаций за 7 дней: {stats['activations_week']}\n"
        f"Активаций за 30 дней: {stats['activations_month']}",
        reply_markup=admin_dashboard_keyboard(),
    )
    await callback.answer()


@router.message(Command("export_clients"))
async def cmd_export_clients(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Недостаточно прав.")
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Client).order_by(Client.id.asc()))
        clients = list(result.scalars().all())

    if not clients:
        await message.answer("Клиентов для экспорта нет.")
        return

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "id",
        "telegram_id",
        "full_name",
        "login",
        "xui_email",
        "xui_uuid",
        "is_active",
        "is_paid",
        "paid_until",
        "trial_used",
        "subscription_link",
        "happ_subscription_url",
        "created_at",
        "updated_at",
    ])

    for client in clients:
        trial_used = "true" if client.notes and "trial_used=true" in client.notes else "false"

        writer.writerow([
            client.id,
            client.telegram_id,
            client.full_name or "",
            client.login or "",
            client.xui_email or "",
            client.xui_uuid or "",
            client.is_active,
            client.is_paid,
            client.paid_until.isoformat(sep=" ") if client.paid_until else "",
            trial_used,
            client.subscription_link or "",
            client.happ_subscription_url or "",
            client.created_at.isoformat(sep=" ") if client.created_at else "",
            client.updated_at.isoformat(sep=" ") if client.updated_at else "",
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    output.close()

    file = BufferedInputFile(csv_bytes, filename="clients_export.csv")

    await message.answer_document(
        file,
        caption=f"Экспорт клиентов: {len(clients)} записей",
    )
