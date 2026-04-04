from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Client
from keyboards.reply import main_reply_keyboard

router = Router()


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


async def get_client_by_telegram_id(telegram_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


@router.message(Command("menu"))
@router.message(F.text == "Меню")
async def show_menu(message: Message):
    client = await get_client_by_telegram_id(str(message.from_user.id))

    await message.answer(
        "<b>Главное меню Freeth</b>\n\n"
        "Основные разделы вынесены ниже. Откройте «Мой доступ», чтобы управлять подпиской, "
        "подключением, устройствами и входом в приложение.",
        reply_markup=main_reply_keyboard(
            message.from_user.id,
            has_active_access=client_has_active_access(client),
            trial_used=client_has_trial_used(client),
        ),
    )
