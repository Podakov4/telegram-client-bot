from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()


def main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Мой профиль", callback_data="my_profile")
    builder.button(text="Моя подписка", callback_data="my_subscription")
    builder.button(text="Помощь", callback_data="help")
    builder.adjust(1)
    return builder.as_markup()


@router.message(Command("menu"))
@router.message(F.text == "Меню")
async def show_menu(message: Message):
    await message.answer(
        "Главное меню:",
        reply_markup=main_menu_keyboard(),
    )