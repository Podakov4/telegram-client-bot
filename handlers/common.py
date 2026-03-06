# handlers/common.py
from aiogram import types, Router, F
from aiogram.filters import Command
from keyboards import reply
import config
from aiogram.fsm.context import FSMContext

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Команда /start"""
    user_id = message.from_user.id

    if user_id in config.ADMIN_IDS:
        text = (
            "👋 <b>Привет, Админ!</b>\n\n"
            "Я бот для управления клиентами.\n\n"
            "Выберите действие из меню ниже 👇"
        )
        # 🔥 Используем reply_markup вместо reply_markup=inline...
        await message.answer(text, reply_markup=reply.main_menu_keyboard())
    else:
        text = (
            "👋 <b>Привет!</b>\n\n"
            "Я бот для управления клиентов.\n"
            "Свяжитесь с администратором для доступа."
        )
        await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Команда /help"""
    text = (
        "📖 <b>Помощь</b>\n\n"
        "<b>Команды:</b>\n"
        "/start - Запустить бота\n"
        "/add_client - Добавить нового клиента\n"
        "/clients - Показать всех клиентов\n"
        "/me - Узнать ваш Telegram ID\n"
        "/help - Эта справка\n\n"
        "<b>Или используйте кнопки в меню!</b>"
    )
    await message.answer(text, reply_markup=reply.back_keyboard())


@router.message(Command("me"))
async def cmd_me(message: types.Message):
    """Команда /me"""
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name

    username_safe = (username or 'не указан').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    full_name_safe = (full_name or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    text = (
        f"👤 <b>Ваша информация:</b>\n\n"
        f"<b>ID:</b> <code>{user_id}</code>\n"
        f"<b>Username:</b> @{username_safe}\n"
        f"<b>Имя:</b> {full_name_safe}"
    )

    await message.answer(text, reply_markup=reply.back_keyboard())


# 🔥 Обработка кнопок меню
@router.message(F.text == "➕ Добавить клиента")
async def menu_add_client(message: types.Message, state: FSMContext):
    """Кнопка 'Добавить клиента'"""
    from aiogram.fsm.context import FSMContext
    await message.answer(
        "📝 <b>Добавление нового клиента</b>\n\n"
        "Введите <b>ФИО клиента</b>:",
        reply_markup=reply.cancel_keyboard()
    )
    await state.set_state("add_client:full_name")


@router.message(F.text == "📋 Список клиентов")
async def menu_clients_list(message: types.Message):
    """Кнопка 'Список клиентов'"""
    from sqlalchemy.orm import Session
    from database import get_db_session, Client

    db: Session = get_db_session()
    try:
        clients = db.query(Client).filter(Client.is_active == True).all()

        if not clients:
            await message.answer(
                "📭 Клиентов пока нет.",
                reply_markup=reply.back_keyboard()
            )
            return

        text = f"📋 <b>Всего клиентов: {len(clients)}</b>\n\n"
        for client in clients[:10]:
            text += (
                f"<b>#{client.id}</b> {client.full_name}\n"
                f"📱 {client.phone}\n"
                f"📧 {client.email or '—'}\n\n"
            )

        if len(clients) > 10:
            text += f"... и ещё {len(clients) - 10} клиентов"

        await message.answer(text, reply_markup=reply.back_keyboard())
    finally:
        db.close()


@router.message(F.text == "📊 Статистика")
async def menu_stats(message: types.Message):
    """Кнопка 'Статистика'"""
    from sqlalchemy.orm import Session
    from database import get_db_session, Client

    db: Session = get_db_session()
    try:
        total = db.query(Client).count()
        active = db.query(Client).filter(Client.is_active == True).count()

        text = (
            "📊 <b>Статистика</b>\n\n"
            f"<b>Всего клиентов:</b> {total}\n"
            f"<b>Активных:</b> {active}\n"
            f"<b>Неактивных:</b> {total - active}"
        )
        await message.answer(text, reply_markup=reply.back_keyboard())
    finally:
        db.close()


@router.message(F.text == "⚙️ Настройки")
async def menu_settings(message: types.Message):
    """Кнопка 'Настройки'"""
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        "Здесь будут настройки бота.\n"
        "Функционал в разработке..."
    )
    await message.answer(text, reply_markup=reply.back_keyboard())


@router.message(F.text == "ℹ️ Помощь")
async def menu_help(message: types.Message):
    """Кнопка 'Помощь'"""
    text = (
        "📖 <b>Помощь</b>\n\n"
        "Используйте кнопки меню для управления ботом.\n\n"
        "Или команды:\n"
        "/start - Главное меню\n"
        "/help - Помощь\n"
        "/me - Мой ID"
    )
    await message.answer(text, reply_markup=reply.back_keyboard())


@router.message(F.text == "❌ Отмена")
async def menu_cancel(message: types.Message, state: FSMContext):
    """Кнопка 'Отмена'"""
    await state.clear()
    await message.answer(
        "❌ Отменено.",
        reply_markup=reply.main_menu_keyboard()
    )


@router.message(F.text == "🔙 В главное меню")
async def menu_back(message: types.Message, state: FSMContext):
    """Кнопка 'Назад в меню'"""
    await state.clear()
    await message.answer(
        "🔙 Главное меню",
        reply_markup=reply.main_menu_keyboard()
    )