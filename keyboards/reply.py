# keyboards/reply.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню (кнопки внизу экрана)"""
    keyboard = [
        [KeyboardButton(text="➕ Добавить клиента")],
        [KeyboardButton(text="📋 Список клиентов")],
        [KeyboardButton(text="📊 Статистика", ), KeyboardButton(text="⚙️ Настройки")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,  # Автоматически подстраивать размер
        one_time_keyboard=False  # Не скрывать после нажатия
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    """Кнопка отмены"""
    keyboard = [
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=True
    )


def back_keyboard() -> ReplyKeyboardMarkup:
    """Кнопка назад"""
    keyboard = [
        [KeyboardButton(text="🔙 В главное меню")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=True
    )