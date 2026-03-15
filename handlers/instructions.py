from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

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
    builder.button(text="Mac", callback_data="instr_mac")
    builder.button(text="Открыть сайт Happ", url=HAPP_SITE_URL)
    builder.adjust(2, 2, 1)
    return builder.as_markup()


@router.message(F.text == "Инструкции")
async def instructions_menu(message: Message):
    await message.answer(
        "Выберите платформу:\n\n"
        "Я покажу, какое приложение установить и как импортировать данные для подключения.",
        reply_markup=instructions_keyboard(),
    )


@router.callback_query(F.data == "instr_ios")
async def instr_ios(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="Скачать Happ для iPhone / iPad", url=HAPP_APPSTORE_URL)
    builder.button(text="Открыть сайт Happ", url=HAPP_SITE_URL)
    builder.adjust(1)

    await callback.message.answer(
        "iPhone / iPad:\n\n"
        "1. Установите Happ из App Store.\n"
        "2. Откройте бота и зайдите в «Моя подписка».\n"
        "3. Нажмите «Показать данные для подключения» или «Показать QR-код».\n"
        "4. Импортируйте данные в Happ.\n"
        "5. Активируйте подключение внутри приложения.",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "instr_android")
async def instr_android(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="Скачать Happ для Android", url=HAPP_GOOGLEPLAY_URL)
    builder.button(text="Открыть сайт Happ", url=HAPP_SITE_URL)
    builder.adjust(1)

    await callback.message.answer(
        "Android:\n\n"
        "1. Установите Happ из Google Play.\n"
        "2. Откройте бота и зайдите в «Моя подписка».\n"
        "3. Нажмите «Показать данные для подключения» или «Показать QR-код».\n"
        "4. Импортируйте данные в Happ.\n"
        "5. Включите подключение внутри приложения.\n\n"
        "Чаще всего удобнее импортировать QR-код.",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "instr_windows")
async def instr_windows(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="Скачать Happ для Windows", url=HAPP_DESKTOP_RELEASES_URL)
    builder.button(text="Открыть сайт Happ", url=HAPP_SITE_URL)
    builder.adjust(1)

    await callback.message.answer(
        "Windows:\n\n"
        "1. Скачайте Happ для Windows.\n"
        "2. Установите и откройте приложение.\n"
        "3. В боте откройте «Моя подписка».\n"
        "4. Возьмите данные для подключения или QR-код.\n"
        "5. Импортируйте их в Happ и подключитесь.\n\n"
        "На ПК обычно удобнее вставить данные вручную.",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "instr_mac")
async def instr_mac(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="Скачать Happ для Mac", url=HAPP_DESKTOP_RELEASES_URL)
    builder.button(text="Открыть сайт Happ", url=HAPP_SITE_URL)
    builder.adjust(1)

    await callback.message.answer(
        "Mac:\n\n"
        "1. Скачайте Happ для macOS.\n"
        "2. Установите и откройте приложение.\n"
        "3. В боте откройте «Моя подписка».\n"
        "4. Импортируйте данные для подключения или QR-код в Happ.\n"
        "5. Включите подключение.\n\n"
        "Если система запросит разрешения для работы приложения, подтвердите их.",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "open_instructions_from_support")
async def open_instructions_from_support(callback: CallbackQuery):
    await callback.message.answer(
        "Выберите платформу:\n\n"
        "Я покажу, какое приложение установить и как импортировать данные для подключения.",
        reply_markup=instructions_keyboard(),
    )
    await callback.answer()