# handlers/client.py
from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.orm import Session
from database import get_db_session, Client
import config
from aiogram.types import CallbackQuery
from keyboards import inline

router = Router()

# Машина состояний для добавления клиента
class AddClient(StatesGroup):
    full_name = State()
    phone = State()
    email = State()
    notes = State()

@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена через кнопку"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Отменено.",
        reply_markup=inline.main_menu_keyboard()
    )
@router.message(Command("add_client"))
async def cmd_add_client(message: types.Message, state: FSMContext):
    """Начать добавление клиента"""
    user_id = message.from_user.id
    
    # Проверка на админа
    if user_id not in config.ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    await message.answer(
        "📝 **Добавление нового клиента**\n\n"
        "Введите **ФИО клиента** (или /cancel для отмены):",
        parse_mode="HTML"
    )
    await state.set_state(AddClient.full_name)

@router.message(AddClient.full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    """Обработка ФИО"""
    if message.text == '/cancel':
        await state.clear()
        await message.answer("❌ Отменено.")
        return
    
    await state.update_data(full_name=message.text)
    await message.answer(
        "📱 Введите **номер телефона** (или /cancel):",
        parse_mode="HTML"
    )
    await state.set_state(AddClient.phone)

@router.message(AddClient.phone)
async def process_phone(message: types.Message, state: FSMContext):
    """Обработка телефона"""
    if message.text == '/cancel':
        await state.clear()
        await message.answer("❌ Отменено.")
        return
    
    await state.update_data(phone=message.text)
    await message.answer(
        "📧 Введите **email** (или /cancel, или пропустите нажав /skip):",
        parse_mode="HTML"
    )
    await state.set_state(AddClient.email)

@router.message(AddClient.email)
async def process_email(message: types.Message, state: FSMContext):
    """Обработка email"""
    if message.text == '/cancel':
        await state.clear()
        await message.answer("❌ Отменено.")
        return
    
    if message.text == '/skip':
        email = None
    else:
        email = message.text
    
    await state.update_data(email=email)
    await message.answer(
        "📝 Введите **заметки** (или /skip, или /cancel):",
        parse_mode="HTML"
    )
    await state.set_state(AddClient.notes)

@router.message(AddClient.notes)
async def process_notes(message: types.Message, state: FSMContext):
    """Обработка заметок и сохранение"""
    if message.text == '/cancel':
        await state.clear()
        await message.answer("❌ Отменено.")
        return
    
    # Получаем данные
    data = await state.get_data()
    notes = message.text if message.text != '/skip' else None
    
    # Сохраняем в БД
    db: Session = get_db_session()
    try:
        new_client = Client(
            telegram_id=str(message.from_user.id),
            full_name=data['full_name'],
            phone=data['phone'],
            email=data['email'],
            notes=notes
        )
        db.add(new_client)
        db.commit()
        db.refresh(new_client)
        
        await message.answer(
            f"✅ **Клиент добавлен!**\n\n"
            f"**ID:** {new_client.id}\n"
            f"**ФИО:** {new_client.full_name}\n"
            f"**Телефон:** {new_client.phone}\n"
            f"**Email:** {new_client.email or 'не указан'}\n"
            f"**Заметки:** {notes or 'нет'}",
            parse_mode="HTML"
        )
    finally:
        db.close()
        await state.clear()

@router.message(Command("clients"))
async def cmd_clients(message: types.Message):
    """Показать всех клиентов"""
    user_id = message.from_user.id
    
    if user_id not in config.ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    db: Session = get_db_session()
    try:
        clients = db.query(Client).filter(Client.is_active == True).all()
        
        if not clients:
            await message.answer("📭 Клиентов пока нет.")
            return
        
        text = f"📋 **Всего клиентов: {len(clients)}**\n\n"
        for client in clients[:10]:  # Показываем первых 10
            text += (
                f"**#{client.id}** {client.full_name}\n"
                f"📱 {client.phone}\n"
                f"📧 {client.email or '—'}\n\n"
            )
        
        if len(clients) > 10:
            text += f"... и ещё {len(clients) - 10} клиентов"
        
        await message.answer(text, parse_mode="HTML")
    finally:
        db.close()

@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    """Отмена текущего действия"""
    await state.clear()
    await message.answer("❌ Отменено.")
