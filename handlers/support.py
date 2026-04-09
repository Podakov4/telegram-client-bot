from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import SUPPORT_USERNAME, SUPPORT_URL

router = Router()


def support_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Написать в поддержку", url=SUPPORT_URL)
    builder.button(text="Частые вопросы", callback_data="support_faq")
    builder.button(text="Как подключить", callback_data="open_instructions_from_support")
    builder.button(text="Документы", callback_data="support_docs")
    builder.adjust(1)
    return builder.as_markup()


def support_back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Написать в поддержку", url=SUPPORT_URL)
    builder.button(text="Назад", callback_data="support_back")
    builder.adjust(1)
    return builder.as_markup()


def support_docs_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Пользовательское соглашение", callback_data="doc_user_agreement")
    builder.button(text="Политика возвратов", callback_data="doc_refund_policy")
    builder.button(text="Политика конфиденциальности", callback_data="doc_privacy_policy")
    builder.button(text="Назад", callback_data="support_back")
    builder.adjust(1)
    return builder.as_markup()


@router.message(Command("support"))
@router.message(F.text == "Поддержка")
async def support_menu(message: Message):
    await message.answer(
        "<b>Поддержка Freeth</b>\n\n"
        "Если есть вопрос по подключению, доступу, оплате или приложению — выберите нужный вариант ниже.",
        reply_markup=support_keyboard(),
    )


@router.callback_query(F.data == "support_back")
async def support_back(callback: CallbackQuery):
    await callback.message.answer(
        "<b>Поддержка Freeth</b>\n\n"
        "Если есть вопрос по подключению, доступу, оплате или приложению — выберите нужный вариант ниже.",
        reply_markup=support_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "support_docs")
async def support_docs(callback: CallbackQuery):
    await callback.message.answer(
        "<b>Документы Freeth</b>\n\n"
        "Выберите нужный документ ниже.",
        reply_markup=support_docs_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "support_faq")
async def support_faq(callback: CallbackQuery):
    await callback.message.answer(
        "<b>Частые вопросы</b>\n\n"
        "<b>Как получить доступ?</b>\n"
        "Нажмите <b>«Попробовать 7 дней»</b> или <b>«Продлить доступ»</b>.\n\n"
        "<b>Где взять данные для подключения?</b>\n"
        "Откройте <b>«Мой доступ»</b> и выберите:\n"
        "• Подключить в Happ\n"
        "• Показать QR-код\n"
        "• Показать данные для подключения\n\n"
        "<b>Как войти в приложение?</b>\n"
        "Откройте <b>«Мой доступ»</b> → <b>«Войти в приложение»</b>.\n\n"
        "<b>Я удалил переписку и не вижу кнопку запуска</b>\n"
        "Отправьте команду <code>/start</code>, затем откройте <b>«Мой доступ»</b>.\n\n"
        "<b>Не получается подключиться</b>\n"
        "Откройте <b>«Как подключить»</b> или напишите в поддержку.\n\n"
        "<b>Оплатил, но доступ не появился</b>\n"
        "Проверьте раздел <b>«Мой доступ»</b>. Если доступ не появился, напишите в поддержку.\n\n"
        f"Поддержка: {SUPPORT_USERNAME}",
        reply_markup=support_back_keyboard(),
    )
    await callback.answer()