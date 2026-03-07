# keyboards/inline.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню"""
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить подписку", callback_data="pay_subscription")
    builder.button(text="🔗 Моя VPN ссылка", callback_data="get_vpn")
    builder.button(text="👤 Мой профиль", callback_data="profile")
    builder.button(text="❓ Помощь", callback_data="help")
    builder.adjust(1, 1, 2)  # По 1 кнопке в ряду, последние 2 вместе
    return builder.as_markup()

def payment_keyboard() -> InlineKeyboardMarkup:
    """Кнопки оплаты"""
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить 300₽/мес", callback_data="pay_300")
    builder.button(text="💳 Оплатить 800₽/3 мес", callback_data="pay_800")
    builder.button(text="💳 Оплатить 3000₽/год", callback_data="pay_3000")
    builder.button(text="❌ Отмена", callback_data="cancel_payment")
    builder.adjust(1, 1, 1, 1)
    return builder.as_markup()

def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Кнопка назад в меню"""
    builder = InlineKeyboardBuilder()
    builder.button(text=" Главное меню", callback_data="main_menu")
    return builder.as_markup()

def vpn_ready_keyboard(vpn_link: str) -> InlineKeyboardMarkup:
    """Кнопка для копирования VPN ссылки"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Скопировать ссылку", callback_data=f"copy_vpn:{vpn_link[:50]}")
    builder.button(text="🏠 Главное меню", callback_data="main_menu")
    builder.adjust(1, 1)
    return builder.as_markup()