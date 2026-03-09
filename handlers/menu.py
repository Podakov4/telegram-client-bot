from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from keyboards.reply import main_reply_keyboard

router = Router()


@router.message(Command("menu"))
@router.message(F.text == "Меню")
async def show_menu(message: Message):
    await message.answer(
        "Главное меню:",
        reply_markup=main_reply_keyboard(message.from_user.id),
    )