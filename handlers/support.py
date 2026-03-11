from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import SUPPORT_USERNAME, SUPPORT_URL

router = Router()


def support_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Написать в поддержку", url=SUPPORT_URL)
    builder.button(text="Частые проблемы", callback_data="support_faq")
    builder.button(text="Открыть инструкции", callback_data="open_instructions_from_support")
    builder.adjust(1)
    return builder.as_markup()


def support_faq_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="VPN не подключается", callback_data="faq_vpn_not_connecting")
    builder.button(text="QR не импортируется", callback_data="faq_qr_import")
    builder.button(text="Ссылка не открывается", callback_data="faq_link_not_opening")
    builder.button(text="Подписка активна, но нет интернета", callback_data="faq_no_internet")
    builder.button(text="Как продлить подписку", callback_data="faq_how_renew")
    builder.button(text="Назад в поддержку", callback_data="support_back")
    builder.adjust(1)
    return builder.as_markup()


@router.message(F.text == "Поддержка")
async def support_message(message: Message):
    await message.answer(
        "Поддержка\n\n"
        f"Связь: {SUPPORT_USERNAME}\n\n"
        "Если возникла проблема, сразу приложите:\n"
        "• ваш Telegram ID или имя в боте\n"
        "• описание проблемы\n"
        "• скриншот ошибки, если он есть\n"
        "• устройство: iPhone / Android / Windows / Mac\n\n"
        "Также можно открыть инструкции или частые вопросы ниже.",
        reply_markup=support_keyboard(),
    )


@router.callback_query(F.data == "support_back")
async def support_back(callback: CallbackQuery):
    await callback.message.answer(
        "Поддержка:\n\n"
        f"Связь: {SUPPORT_USERNAME}\n\n"
        "Выберите действие ниже.",
        reply_markup=support_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "support_faq")
async def support_faq(callback: CallbackQuery):
    await callback.message.answer(
        "Частые проблемы:\n\n"
        "Выберите подходящий вариант ниже.",
        reply_markup=support_faq_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "faq_vpn_not_connecting")
async def faq_vpn_not_connecting(callback: CallbackQuery):
    await callback.message.answer(
        "VPN не подключается:\n\n"
        "1. Проверьте, что подписка активна в разделе «Мой профиль».\n"
        "2. Откройте «Моя подписка» и заново импортируйте ссылку или QR.\n"
        "3. Убедитесь, что в приложении Happ включено подключение.\n"
        "4. Попробуйте выключить и снова включить VPN.\n"
        "5. Если не помогло — напишите в поддержку и приложите скриншот.",
        reply_markup=support_faq_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "faq_qr_import")
async def faq_qr_import(callback: CallbackQuery):
    await callback.message.answer(
        "QR не импортируется:\n\n"
        "1. Откройте «Моя подписка» и нажмите «Показать QR» еще раз.\n"
        "2. Убедитесь, что QR целиком виден на экране.\n"
        "3. Попробуйте вместо QR использовать кнопку «Показать ссылку».\n"
        "4. Если импорт все равно не работает — напишите в поддержку.",
        reply_markup=support_faq_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "faq_link_not_opening")
async def faq_link_not_opening(callback: CallbackQuery):
    await callback.message.answer(
        "Ссылка не открывается:\n\n"
        "Это нормально: Telegram не умеет открывать vless:// напрямую кнопкой.\n\n"
        "Что делать:\n"
        "1. Откройте «Моя подписка».\n"
        "2. Нажмите «Показать ссылку».\n"
        "3. Скопируйте ссылку вручную.\n"
        "4. Импортируйте ее в Happ.\n\n"
        "Либо используйте QR-код — это обычно удобнее.",
        reply_markup=support_faq_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "faq_no_internet")
async def faq_no_internet(callback: CallbackQuery):
    await callback.message.answer(
        "Подписка активна, но интернета нет:\n\n"
        "1. Переподключите VPN в приложении.\n"
        "2. Проверьте, что импортирован именно свежий конфиг из бота.\n"
        "3. Попробуйте удалить старый конфиг и импортировать заново.\n"
        "4. Убедитесь, что на устройстве есть обычный интернет без VPN.\n"
        "5. Если проблема остается — напишите в поддержку.",
        reply_markup=support_faq_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "faq_how_renew")
async def faq_how_renew(callback: CallbackQuery):
    await callback.message.answer(
        "Как продлить подписку:\n\n"
        "1. Откройте «Моя подписка».\n"
        "2. Нажмите «Продлить подписку».\n"
        "3. Выберите тариф: 1, 3 или 12 месяцев.\n\n"
        "Также можно продлить через кнопку «Оплата» в главном меню.",
        reply_markup=support_faq_keyboard(),
    )
    await callback.answer()