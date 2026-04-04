from datetime import datetime

from aiogram import Router
from aiogram.filters import CommandStart
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


def keyboard_for_client(client: Client | None, user_id: int):
    return main_reply_keyboard(
        user_id,
        has_active_access=client_has_active_access(client),
        trial_used=client_has_trial_used(client),
    )


@router.message(CommandStart())
async def cmd_start(message: Message):
    telegram_id = str(message.from_user.id)
    full_name = message.from_user.full_name

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == telegram_id)
        )
        client = result.scalar_one_or_none()

        is_new_user = client is None

        if client is None:
            client = Client(
                telegram_id=telegram_id,
                full_name=full_name,
                is_active=False,
                is_paid=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(client)
            await session.commit()
        elif client.full_name != full_name:
            client.full_name = full_name
            client.updated_at = datetime.utcnow()
            await session.commit()

    if is_new_user:
        await message.answer(
            f"Здравствуйте, {full_name}!\n\n"
            "Добро пожаловать в <b>Freeth</b>.\n\n"
            "Здесь вы можете:\n"
            "• получить пробный доступ на 7 дней\n"
            "• подключить телефон или компьютер\n"
            "• управлять доступом и устройствами\n"
            "• позже входить в приложение как тот же клиент\n\n"
            "Начните с одного из шагов ниже.",
            reply_markup=keyboard_for_client(client, message.from_user.id),
        )
        return

    if client_has_active_access(client):
        text = (
            f"С возвращением, {full_name}!\n\n"
            "Откройте <b>«Мой доступ»</b>, чтобы посмотреть статус, подключение, устройства "
            "и вход в приложение."
        )
    else:
        text = (
            f"С возвращением, {full_name}!\n\n"
            "Сейчас вы можете открыть <b>«Мой доступ»</b>, активировать пробный период "
            "или продлить доступ."
        )

    await message.answer(
        text,
        reply_markup=keyboard_for_client(client, message.from_user.id),
    )
