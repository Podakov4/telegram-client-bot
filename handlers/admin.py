from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, or_

from config import ADMIN_IDS
from database.db import AsyncSessionLocal
from database.models import Client, SubscriptionHistory
from services.client_access import create_vpn_access_for_client
from services.payments import activate_subscription, deactivate_subscription
from services.subscriptions import get_expiring_clients, get_expired_clients

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def admin_dashboard_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Истекают", callback_data="admin_dashboard_expiring")
    builder.button(text="Просрочены", callback_data="admin_dashboard_expired")
    builder.button(text="На trial", callback_data="admin_dashboard_trial")
    builder.button(text="Активные", callback_data="admin_dashboard_active")
    builder.button(text="Напомнить истекающим", callback_data="admin_notify_expiring")
    builder.button(text="Напомнить просроченным", callback_data="admin_notify_expired")
    builder.button(text="Как искать клиента", callback_data="admin_dashboard_find_help")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def admin_client_actions_keyboard(client_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="Продлить 1 месяц", callback_data=f"admin_extend_1:{client_id}")
    builder.button(text="Продлить 3 месяца", callback_data=f"admin_extend_3:{client_id}")
    builder.button(text="Продлить 12 месяцев", callback_data=f"admin_extend_12:{client_id}")
    builder.button(text="Пересоздать доступ", callback_data=f"admin_recreate:{client_id}")
    builder.button(text="История подписок", callback_data=f"admin_history:{client_id}")
    builder.button(text="Отключить", callback_data=f"admin_disable:{client_id}")
    builder.adjust(1)
    return builder.as_markup()


def admin_search_results_keyboard(clients: list[Client]):
    builder = InlineKeyboardBuilder()
    for client in clients:
        title = f"{client.full_name or 'Без имени'} | tg:{client.telegram_id}"
        builder.button(text=title[:64], callback_data=f"admin_open:{client.id}")
    builder.adjust(1)
    return builder.as_markup()


def clients_list_keyboard(clients: list[Client]):
    builder = InlineKeyboardBuilder()
    for client in clients:
        title = f"{client.full_name or 'Без имени'} | tg:{client.telegram_id}"
        builder.button(text=title[:64], callback_data=f"admin_open:{client.id}")
    builder.adjust(1)
    return builder.as_markup()


def renewal_keyboard():
    builder = InlineKeyboardBuilder()
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
        f"Активно до: {paid_until_text}\n"
        f"Осталось: {days_left_text}\n"
        f"Ссылка: {'Есть' if client.subscription_link else 'Нет'}"
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


async def get_client_by_db_id(client_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id)
        )
        return result.scalar_one_or_none()


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


async def send_expiring_notice(bot: Bot, client: Client) -> bool:
    try:
        paid_until = (
            client.paid_until.strftime("%Y-%m-%d %H:%M")
            if client.paid_until
            else "скоро"
        )

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


async def send_expired_notice(bot: Bot, client: Client) -> bool:
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
        return True
    except Exception:
        return False


@router.message(Command("admin"))
async def admin_menu(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Недостаточно прав.")
        return

    await message.answer(
        "Админ-дашборд:",
        reply_markup=admin_dashboard_keyboard(),
    )


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

    clients = await get_expired_clients()

    if not clients:
        await callback.message.answer("Нет просроченных подписок.")
        await callback.answer()
        return

    await callback.message.answer(
        f"Просроченные подписки: {len(clients)}",
        reply_markup=clients_list_keyboard(clients[:20]),
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

    clients = await get_expired_clients()

    if not clients:
        await callback.message.answer("Нет клиентов с истекшей подпиской.")
        await callback.answer()
        return

    sent = 0
    failed = 0

    for client in clients:
        ok = await send_expired_notice(bot, client)
        if ok:
            sent += 1
        else:
            failed += 1

    await callback.message.answer(
        f"Готово.\n\nСообщений отправлено: {sent}\nОшибок: {failed}"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_open:"))
async def cb_admin_open(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":")[1])
    client = await get_client_by_db_id(client_id)

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
    client = await get_client_by_db_id(client_id)

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


@router.callback_query(F.data.startswith("admin_extend_"))
async def cb_admin_extend(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    action, client_id_str = callback.data.split(":")
    months = int(action.rsplit("_", 1)[1])
    client_id = int(client_id_str)

    client = await get_client_by_db_id(client_id)
    if not client:
        await callback.message.answer("Клиент не найден.")
        await callback.answer()
        return

    ok = await activate_subscription(client.telegram_id, months=months)
    if not ok:
        await callback.message.answer("Не удалось продлить подписку.")
        await callback.answer()
        return

    updated = await get_client_by_db_id(client_id)
    await callback.message.answer(
        f"Подписка продлена на {months} мес.\n\n{format_client_card(updated)}",
        reply_markup=admin_client_actions_keyboard(updated.id),
    )
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("admin_recreate:"))
async def cb_admin_recreate(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    client_id = int(callback.data.split(":")[1])
    client = await get_client_by_db_id(client_id)
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
            db_client.xui_email = None
            db_client.login = None
            db_client.updated_at = datetime.utcnow()
            await session.commit()

    ok = await create_vpn_access_for_client(client.telegram_id)
    if not ok:
        await callback.message.answer("Не удалось пересоздать доступ.")
        await callback.answer()
        return

    updated = await get_client_by_db_id(client_id)
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
    client = await get_client_by_db_id(client_id)
    if not client:
        await callback.message.answer("Клиент не найден.")
        await callback.answer()
        return

    ok = await deactivate_subscription(client.telegram_id)
    if not ok:
        await callback.message.answer("Не удалось отключить подписку.")
        await callback.answer()
        return

    updated = await get_client_by_db_id(client_id)
    await callback.message.answer(
        f"Подписка отключена.\n\n{format_client_card(updated)}",
        reply_markup=admin_client_actions_keyboard(updated.id),
    )
    await callback.answer("Готово")