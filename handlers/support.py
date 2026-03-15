from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import SUPPORT_USERNAME, SUPPORT_URL

router = Router()


def support_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Написать в поддержку", url=SUPPORT_URL)
    builder.button(text="Показать инструкции", callback_data="open_instructions_from_support")
    builder.button(text="Частые вопросы", callback_data="support_faq")
    builder.adjust(1)
    return builder.as_markup()


def support_back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Написать в поддержку", url=SUPPORT_URL)
    builder.button(text="Назад", callback_data="support_back")
    builder.adjust(1)
    return builder.as_markup()


@router.message(F.text == "Поддержка")
async def support_menu(message: Message):
    await message.answer(
        "Поддержка Freeth\n\n"
        "Если у вас возникли вопросы по оплате, подписке или подключению, "
        "напишите в поддержку или откройте раздел с частыми вопросами.",
        reply_markup=support_keyboard(),
    )


@router.callback_query(F.data == "support_back")
async def support_back(callback: CallbackQuery):
    await callback.message.answer(
        "Поддержка Freeth\n\n"
        "Если у вас возникли вопросы по оплате, подписке или подключению, "
        "напишите в поддержку или откройте раздел с частыми вопросами.",
        reply_markup=support_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "support_faq")
async def support_faq(callback: CallbackQuery):
    await callback.message.answer(
        "Частые вопросы\n\n"
        "1. Как получить доступ?\n"
        "Откройте раздел «Оплата» или активируйте пробный период на 7 дней.\n\n"
        "2. Где взять данные для подключения?\n"
        "Откройте «Моя подписка», затем выберите:\n"
        "• Показать данные для подключения\n"
        "• Показать QR-код\n\n"
        "3. Что делать, если не получается подключиться?\n"
        "Проверьте инструкцию для вашего устройства в разделе «Инструкции».\n"
        "Если проблема сохраняется, напишите в поддержку.\n\n"
        "4. Что делать, если оплатил, но доступ не появился?\n"
        "Нажмите «Проверить оплату» ещё раз. "
        "Если доступ не активировался, обратитесь в поддержку.\n\n"
        f"Поддержка: {SUPPORT_USERNAME}",
        reply_markup=support_back_keyboard(),
    )
    await callback.answer()