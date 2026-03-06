# keyboards/inline.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню админа"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="➕ Добавить клиента", callback_data="add_client"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 Список клиентов", callback_data="clients_list"),
    )
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"),
    )

    return builder.as_markup()


def client_actions_keyboard(client_id: int) -> InlineKeyboardMarkup:
    """Кнопки действий с клиентом"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_client:{client_id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_client:{client_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="clients_list"),
    )

    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    """Кнопка отмены"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
    )
    return builder.as_markup()


def back_keyboard() -> InlineKeyboardMarkup:
    """Кнопка назад"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔙 В главное меню", callback_data="main_menu"),
    )
    return builder.as_markup()