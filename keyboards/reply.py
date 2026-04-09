from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from config import ADMIN_IDS


def main_reply_keyboard(
    user_id: int,
    *,
    has_active_access: bool = False,
    trial_used: bool = False,
) -> ReplyKeyboardMarkup:
    primary_action = "Продлить доступ" if has_active_access or trial_used else "Попробовать 7 дней"

    rows = [
        [
            KeyboardButton(text="Мой доступ"),
            KeyboardButton(text="Как подключить"),
        ],
        [
            KeyboardButton(text=primary_action),
            KeyboardButton(text="Поддержка"),
        ],
        [
            KeyboardButton(text="Помощь"),
        ],
    ]

    if user_id in ADMIN_IDS:
        rows.append([KeyboardButton(text="Админ")])

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие",
    )