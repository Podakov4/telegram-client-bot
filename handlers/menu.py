# handlers/menu.py
from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.orm import Session
from database import get_db_session, Client
from keyboards import inline
import config

router = Router()


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery):
    """Главное меню"""
    text = (
        "📋 <b>Главное меню</b>\n\n"
        "Выберите действие:"
    )
    await callback.message.edit_text(text, reply_markup=inline.main_menu_keyboard())


@router.callback_query(F.data == "add_client")
async def cb_add_client(callback: CallbackQuery, state: FSMContext):
    """Добавление клиента - старт"""
    await callback.message.edit_text(
        "📝 <b>Добавление нового клиента</b>\n\n"
        "Введите <b>ФИО клиента</b> (или нажмите Отмена):",
        reply_markup=inline.cancel_keyboard()
    )
    await state.set_state("add_client:full_name")


@router.callback_query(F.data == "clients_list")
async def cb_clients_list(callback: CallbackQuery):
    """Список клиентов"""
    db: Session = get_db_session()
    try:
        clients = db.query(Client).filter(Client.is_active == True).all()

        if not clients:
            await callback.message.edit_text(
                "📭 Клиентов пока нет.",
                reply_markup=inline.back_keyboard()
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

        await callback.message.edit_text(text, reply_markup=inline.back_keyboard())
    finally:
        db.close()


@router.callback_query(F.data == "stats")
async def cb_stats(callback: CallbackQuery):
    """Статистика"""
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
        await callback.message.edit_text(text, reply_markup=inline.back_keyboard())
    finally:
        db.close()


@router.callback_query(F.data == "settings")
async def cb_settings(callback: CallbackQuery):
    """Настройки"""
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        "Здесь будут настройки бота.\n"
        "Функционал в разработке..."
    )
    await callback.message.edit_text(text, reply_markup=inline.back_keyboard())


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена действия"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Отменено.",
        reply_markup=inline.main_menu_keyboard()
    )