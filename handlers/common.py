from datetime import datetime

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Client
from keyboards.reply import main_reply_keyboard

router = Router()


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

    if is_new_user:
        await message.answer(
            f"Здравствуйте, {full_name}!\n\n"
            "Добро пожаловать в Freeth VPN.\n\n"
            "Здесь вы можете:\n"
            "• активировать пробный период на 7 дней\n"
            "• оформить подписку\n"
            "• получить VLESS-ссылку и QR-код\n"
            "• продлить доступ в пару нажатий\n\n"
            "Начните с кнопок ниже.",
            reply_markup=main_reply_keyboard(message.from_user.id),
        )
    else:
        await message.answer(
            f"С возвращением, {full_name}!\n\n"
            "Выберите действие в меню ниже.",
            reply_markup=main_reply_keyboard(message.from_user.id),
        )