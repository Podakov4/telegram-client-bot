from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, or_

from config import ADMIN_IDS
from database.db import AsyncSessionLocal
from database.models import Client
from services.client_access import create_vpn_access_for_client
from services.payments import activate_subscription, deactivate_subscription

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def admin_client_actions_keyboard(client_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="Продлить 1 месяц", callback_data=f"admin_extend_1:{client_id}")
    builder.button(text="Продлить 3 месяца", callback_data=f"admin_extend_3:{client_id}")
    builder.button(text="Продлить 12 месяцев", callback_data=f"admin_extend_12:{client_id}")
    builder.button(text="Пересоздать доступ", callback_data=f"admin_recreate:{client_id}")
    builder.button(text="Отключить", callback_data=f"admin_disable:{client_id}")
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


async def get_client_by_db_id(client_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id)
        )
        return result.scalar_one_or_none()


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


@router.message(Command("find"))
async def cmd_find(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Недостаточно прав.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /find <telegram_id | id | имя>")
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

    for client in clients:
        await message.answer(
            format_client_card(client),
            reply_markup=admin_client_actions_keyboard(client.id),
        )


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