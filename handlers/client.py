from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command
from sqlalchemy import select

from config import ADMIN_IDS
from database.db import AsyncSessionLocal
from database.models import Client
from services.client_access import create_vpn_access_for_client
from services.payments import mark_client_paid, mark_client_unpaid
from handlers.menu import main_menu_keyboard

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
                "Нажмите «Моя подписка» чуть позже или создайте доступ кнопкой администратора."
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
async def cmd_profile(message: Message):
    client = await get_client_by_telegram_id(str(message.from_user.id))

    if client is None:
        await message.answer("Профиль не найден. Нажмите /start")
        return

    await message.answer(format_profile_text(client))


@router.message(Command("subscription"))
async def cmd_subscription(message: Message):
    client = await get_client_by_telegram_id(str(message.from_user.id))

    if client is None:
        await message.answer("Профиль не найден. Нажмите /start")
        return

    await message.answer(format_subscription_text(client))


@router.callback_query(F.data == "my_profile")
async def cb_my_profile(callback: CallbackQuery):
    client = await get_client_by_telegram_id(str(callback.from_user.id))

    if client is None:
        await callback.message.answer("Профиль не найден. Нажмите /start")
        await callback.answer()
        return

    await callback.message.answer(format_profile_text(client))
    await callback.answer()


@router.callback_query(F.data == "my_subscription")
async def cb_my_subscription(callback: CallbackQuery):
    client = await get_client_by_telegram_id(str(callback.from_user.id))

    if client is None:
        await callback.message.answer("Профиль не найден. Нажмите /start")
        await callback.answer()
        return

    await callback.message.answer(format_subscription_text(client))
    await callback.answer()


@router.callback_query(F.data == "request_access")
async def cb_request_access(callback: CallbackQuery):
    await callback.message.answer(
        "Заявка на доступ отправлена.\n"
        "После подтверждения оплаты администратором ссылка появится в разделе «Моя подписка».",
        reply_markup=main_menu_keyboard(callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_pay_me")
async def cb_admin_pay_me(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    telegram_id = str(callback.from_user.id)
    ok = await mark_client_paid(telegram_id)

    if not ok:
        await callback.message.answer("Не удалось подтвердить оплату.")
        await callback.answer()
        return

    await callback.message.answer("Оплата подтверждена.")
    await callback.answer("Готово")


@router.callback_query(F.data == "admin_create_access_me")
async def cb_admin_create_access_me(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    telegram_id = str(callback.from_user.id)
    ok = await create_vpn_access_for_client(telegram_id)

    if not ok:
        await callback.message.answer("Не удалось создать доступ в 3x-ui.")
        await callback.answer()
        return

    client = await get_client_by_telegram_id(telegram_id)
    await callback.message.answer("Доступ создан.")
    await callback.message.answer(format_subscription_text(client))
    await callback.answer("Готово")


@router.callback_query(F.data == "admin_unpay_me")
async def cb_admin_unpay_me(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    telegram_id = str(callback.from_user.id)
    ok = await mark_client_unpaid(telegram_id)

    if not ok:
        await callback.message.answer("Не удалось отключить подписку.")
        await callback.answer()
        return

    await callback.message.answer("Подписка отключена.")
    await callback.answer("Готово")


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    await callback.message.answer(
        "Доступные действия:\n"
        "• Мой профиль\n"
        "• Моя подписка\n"
        "• Запросить доступ\n\n"
        "Для администратора также доступны:\n"
        "• Подтвердить оплату\n"
        "• Создать доступ\n"
        "• Отключить подписку"
    )
    await callback.answer()