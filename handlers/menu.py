from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS

router = Router()


def main_menu_keyboard(user_id: int):
    builder = InlineKeyboardBuilder()

    builder.button(text="Мой профиль", callback_data="my_profile")
    builder.button(text="Моя подписка", callback_data="my_subscription")
    builder.button(text="Запросить доступ", callback_data="request_access")
    builder.button(text="Помощь", callback_data="help")

    if user_id in ADMIN_IDS:
        builder.button(text="✅ Подтвердить оплату", callback_data="admin_pay_me")
        builder.button(text="➕ Создать доступ", callback_data="admin_create_access_me")
        builder.button(text="⛔ Отключить подписку", callback_data="admin_unpay_me")

    builder.adjust(1)
    return builder.as_markup()


@router.message(Command("menu"))
@router.message(F.text == "Меню")
async def show_menu(message: Message):
    await message.answer(
        "Главное меню:",
        reply_markup=main_menu_keyboard(message.from_user.id),
    )