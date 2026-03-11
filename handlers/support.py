from aiogram import Router, F
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import SUPPORT_USERNAME, SUPPORT_URL
from keyboards.reply import main_reply_keyboard

router = Router()


def support_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Написать в поддержку", url=SUPPORT_URL)
    builder.button(text="Открыть инструкции", callback_data="open_instructions_from_support")
    builder.adjust(1)
    return builder.as_markup()


@router.message(F.text == "Поддержка")
async def support_message(message: Message):
    await message.answer(
        "Поддержка:\n\n"
        f"Связь: {SUPPORT_USERNAME}\n\n"
        "Если что-то не работает, напишите в поддержку и сразу приложите:\n"
        "• ваш Telegram ID или имя в боте\n"
        "• описание проблемы\n"
        "• скриншот ошибки, если она есть\n"
        "• устройство: iPhone / Android / Windows / Mac\n\n"
        "Частые ситуации:\n"
        "• не получается импортировать ссылку\n"
        "• QR не сканируется\n"
        "• VPN не подключается\n"
        "• подписка активна, но интернет не работает",
        reply_markup=support_keyboard(),
    )