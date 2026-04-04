from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import SUPPORT_URL

router = Router()

HAPP_SITE_URL = "https://www.happ.su/main/ru"
HAPP_APPSTORE_URL = "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"
HAPP_GOOGLEPLAY_URL = "https://play.google.com/store/apps/details?id=com.happproxy"
HAPP_DESKTOP_RELEASES_URL = "https://github.com/Happ-proxy/happ-desktop/releases"


def instructions_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="iPhone / iPad", callback_data="instr_ios")
    builder.button(text="Android", callback_data="instr_android")
    builder.button(text="Windows", callback_data="instr_windows")
    builder.button(text="macOS", callback_data="instr_mac")
    builder.button(text="Открыть сайт Happ", url=HAPP_SITE_URL)
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def platform_keyboard(download_text: str, download_url: str):
    builder = InlineKeyboardBuilder()
    builder.button(text=download_text, url=download_url)
    builder.button(text="Написать в поддержку", url=SUPPORT_URL)
    builder.adjust(1)
    return builder.as_markup()


@router.message(F.text == "Как подключить")
@router.message(F.text == "Инструкции")
async def instructions_menu(message: Message):
    await message.answer(
        "<b>Как подключить Freeth</b>\n\n"
        "Выберите ваше устройство. Я покажу:\n"
        "• что скачать\n"
        "• как добавить доступ\n"
        "• как включить подключение\n"
        "• как проверить, что все работает",
        reply_markup=instructions_keyboard(),
    )


@router.callback_query(F.data == "instr_ios")
async def instr_ios(callback: CallbackQuery):
    await callback.message.answer(
        "<b>iPhone / iPad</b>\n\n"
        "1. Установите Happ из App Store.\n"
        "2. В боте откройте <b>«Мой доступ»</b>.\n"
        "3. Нажмите <b>«Показать QR-код»</b> или <b>«Данные для подключения»</b>.\n"
        "4. Импортируйте доступ в Happ.\n"
        "5. Включите подключение внутри приложения.\n\n"
        "Если что-то не заработало, напишите в поддержку.",
        reply_markup=platform_keyboard(
            "Скачать Happ для iPhone / iPad",
            HAPP_APPSTORE_URL,
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "instr_android")
async def instr_android(callback: CallbackQuery):
    await callback.message.answer(
        "<b>Android</b>\n\n"
        "1. Установите Happ из Google Play.\n"
        "2. В боте откройте <b>«Мой доступ»</b>.\n"
        "3. Нажмите <b>«Показать QR-код»</b> или <b>«Данные для подключения»</b>.\n"
        "4. Импортируйте доступ в Happ.\n"
        "5. Включите подключение внутри приложения.\n\n"
        "Обычно на Android удобнее импортировать QR-код.",
        reply_markup=platform_keyboard(
            "Скачать Happ для Android",
            HAPP_GOOGLEPLAY_URL,
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "instr_windows")
async def instr_windows(callback: CallbackQuery):
    await callback.message.answer(
        "<b>Windows</b>\n\n"
        "1. Скачайте Happ для Windows.\n"
        "2. Установите и откройте приложение.\n"
        "3. В боте откройте <b>«Мой доступ»</b>.\n"
        "4. Возьмите данные для подключения или QR-код.\n"
        "5. Импортируйте их в Happ и подключитесь.\n\n"
        "На ПК чаще всего удобнее вставить данные вручную.",
        reply_markup=platform_keyboard(
            "Скачать Happ для Windows",
            HAPP_DESKTOP_RELEASES_URL,
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "instr_mac")
async def instr_mac(callback: CallbackQuery):
    await callback.message.answer(
        "<b>macOS</b>\n\n"
        "1. Скачайте Happ для macOS.\n"
        "2. Установите и откройте приложение.\n"
        "3. В боте откройте <b>«Мой доступ»</b>.\n"
        "4. Импортируйте данные для подключения или QR-код в Happ.\n"
        "5. Включите подключение.\n\n"
        "Если система запросит разрешения для работы приложения, подтвердите их.",
        reply_markup=platform_keyboard(
            "Скачать Happ для macOS",
            HAPP_DESKTOP_RELEASES_URL,
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "open_instructions_from_support")
@router.callback_query(F.data == "open_instructions_from_access")
async def open_instructions_from_anywhere(callback: CallbackQuery):
    await callback.message.answer(
        "<b>Как подключить Freeth</b>\n\n"
        "Выберите ваше устройство. Я покажу, что скачать и как импортировать доступ.",
        reply_markup=instructions_keyboard(),
    )
    await callback.answer()
