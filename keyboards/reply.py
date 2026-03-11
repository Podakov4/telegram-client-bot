from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


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
            KeyboardButton(text="Инструкции"),
            KeyboardButton(text="Поддержка"),
        ],
        [
            KeyboardButton(text="Помощь"),
        ],
    ]

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие",
    )