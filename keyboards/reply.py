from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from config import ADMIN_IDS


def main_reply_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    rows = [
        [
            KeyboardButton(text="Мой профиль"),
            KeyboardButton(text="Моя подписка"),
        ],
        [
            KeyboardButton(text="Пробный период 7 дней"),
            KeyboardButton(text="Оплата"),
        ],
        [
            KeyboardButton(text="Помощь"),
        ],
    ]

    if user_id in ADMIN_IDS:
        rows.append(
            [
                KeyboardButton(text="➕ Создать доступ"),
                KeyboardButton(text="⛔ Отключить подписку"),
            ]
        )

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие",
    )