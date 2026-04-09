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
            "• получить пробный доступ\n"
            "• подключить телефон или компьютер\n"
            "• управлять устройствами и подпиской\n"
            "• войти в приложение через Telegram\n\n"
            "Чтобы начать:\n"
            "1. Откройте <b>«Мой доступ»</b>\n"
            "2. При необходимости активируйте пробный период\n"
            "3. Для входа в приложение выберите <b>«Войти в приложение»</b>\n\n"
            "Если вы открыли бот после удаления переписки — просто продолжайте через кнопки ниже.",
            reply_markup=keyboard_for_client(client, message.from_user.id),
        )
        return

    if client_has_active_access(client):
        text = (
            f"С возвращением, {full_name}!\n\n"
            "Откройте <b>«Мой доступ»</b>, чтобы:\n"
            "• посмотреть статус доступа\n"
            "• открыть ссылки для подключения\n"
            "• управлять устройствами\n"
            "• войти в приложение через Telegram\n\n"
            "Для входа в приложение используйте кнопку <b>«Войти в приложение»</b>."
        )
    else:
        text = (
            f"С возвращением, {full_name}!\n\n"
            "Сейчас вы можете:\n"
            "• открыть <b>«Мой доступ»</b>\n"
            "• активировать пробный период\n"
            "• продлить доступ\n"
            "• после активации войти в приложение\n\n"
            "Если вы открыли бот после удаления переписки, просто используйте кнопки ниже."
        )

    await message.answer(
        text,
        reply_markup=keyboard_for_client(client, message.from_user.id),
    )