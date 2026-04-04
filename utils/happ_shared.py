from aiogram.utils.keyboard import InlineKeyboardBuilder

HAPP_SITE_URL = "https://www.happ.su/main/ru"
HAPP_APPSTORE_URL = "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"
HAPP_GOOGLEPLAY_URL = "https://play.google.com/store/apps/details?id=com.happproxy"
HAPP_WINDOWS_URL = "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe"
HAPP_MACOS_URL = "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.macOS.universal.dmg"


def device_selection_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="iPhone / iPad", callback_data="instr_ios")
    builder.button(text="Android", callback_data="instr_android")
    builder.button(text="Windows x64", callback_data="instr_windows")
    builder.button(text="macOS", callback_data="instr_mac")
    builder.button(text="Открыть сайт Happ", url=HAPP_SITE_URL)
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def support_only_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Написать в поддержку", callback_data="open_support_from_instructions")
    builder.adjust(1)
    return builder.as_markup()


def instruction_action_keyboard(platform_key: str):
    builder = InlineKeyboardBuilder()

    if platform_key == "ios":
        builder.button(text="Скачать Happ для iPhone / iPad", url=HAPP_APPSTORE_URL)
    elif platform_key == "android":
        builder.button(text="Скачать Happ для Android", url=HAPP_GOOGLEPLAY_URL)
    elif platform_key == "windows":
        builder.button(text="Скачать Happ для Windows x64", url=HAPP_WINDOWS_URL)
    elif platform_key == "macos":
        builder.button(text="Скачать Happ для macOS", url=HAPP_MACOS_URL)

    builder.button(text="Открыть сайт Happ", url=HAPP_SITE_URL)
    builder.button(text="Написать в поддержку", callback_data="open_support_from_instructions")
    builder.adjust(1)
    return builder.as_markup()


def client_instructions_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Happ для iPhone / iPad", url=HAPP_APPSTORE_URL)
    builder.button(text="Happ для Android", url=HAPP_GOOGLEPLAY_URL)
    builder.button(text="Happ для Windows x64", url=HAPP_WINDOWS_URL)
    builder.button(text="Happ для macOS", url=HAPP_MACOS_URL)
    builder.button(text="Открыть сайт Happ", url=HAPP_SITE_URL)
    builder.adjust(1)
    return builder.as_markup()


def instructions_menu_text() -> str:
    return (
        "<b>Как подключить Freeth</b>\n\n"
        "Выберите ваше устройство.\n"
        "Я покажу, что скачать и как быстро подключить доступ."
    )


def platform_instruction_text(platform_key: str) -> str:
    texts = {
        "ios": (
            "<b>iPhone / iPad</b>\n\n"
            "1. Установите Happ из App Store.\n"
            "2. В боте откройте <b>«Мой доступ»</b>.\n"
            "3. Выберите один из вариантов:\n"
            "• <b>Подключить в Happ</b> — самый быстрый способ\n"
            "• <b>Показать QR-код</b> — удобно, если нужно импортировать вручную\n"
            "• <b>Данные для подключения</b> — если хотите вставить ссылку сами\n"
            "4. Импортируйте доступ в Happ.\n"
            "5. Включите подключение.\n\n"
            "Обычно на iPhone удобнее использовать кнопку подключения или QR-код."
        ),
        "android": (
            "<b>Android</b>\n\n"
            "1. Установите Happ из Google Play.\n"
            "2. В боте откройте <b>«Мой доступ»</b>.\n"
            "3. Выберите один из вариантов:\n"
            "• <b>Подключить в Happ</b> — самый быстрый способ\n"
            "• <b>Показать QR-код</b> — обычно это самый удобный вариант\n"
            "• <b>Данные для подключения</b> — если хотите вставить ссылку сами\n"
            "4. Импортируйте доступ в Happ.\n"
            "5. Включите подключение.\n\n"
            "Чаще всего на Android удобнее подключаться по QR-коду."
        ),
        "windows": (
            "<b>Windows x64</b>\n\n"
            "1. Скачайте и установите Happ для Windows x64.\n"
            "2. В боте откройте <b>«Мой доступ»</b>.\n"
            "3. Выберите один из вариантов:\n"
            "• <b>Подключить в Happ</b>\n"
            "• <b>Показать QR-код</b>\n"
            "• <b>Данные для подключения</b>\n"
            "4. Импортируйте доступ в Happ.\n"
            "5. Включите подключение.\n\n"
            "На ПК чаще всего удобно вставить данные вручную.\n"
            "Для 32-битной Windows официальной сборки сейчас нет."
        ),
        "macos": (
            "<b>macOS</b>\n\n"
            "1. Скачайте Happ для macOS.\n"
            "2. Установите и откройте приложение.\n"
            "3. В боте откройте <b>«Мой доступ»</b>.\n"
            "4. Выберите один из вариантов:\n"
            "• <b>Подключить в Happ</b>\n"
            "• <b>Показать QR-код</b>\n"
            "• <b>Данные для подключения</b>\n"
            "5. Импортируйте доступ и включите подключение.\n\n"
            "Если macOS запросит разрешения для работы приложения, подтвердите их."
        ),
    }
    return texts[platform_key]


def admin_instructions_text(client_name: str | None) -> str:
    name = client_name or "пользователь"
    return (
        f"Здравствуйте, {name}!\n\n"
        "Короткая инструкция по подключению Freeth:\n\n"
        "1. Установите Happ на своё устройство\n"
        "2. В боте откройте <b>«Мой доступ»</b>\n"
        "3. Выберите <b>«Подключить в Happ»</b>, <b>«Показать QR-код»</b> или <b>«Данные для подключения»</b>\n"
        "4. Импортируйте доступ в Happ и включите подключение\n\n"
        "Ниже — прямые ссылки на скачивание Happ для вашей платформы."
    )
