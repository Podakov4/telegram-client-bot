from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.orm import Session
from database import get_db_session, Client
from services.vless import VLESSManager
from keyboards import inline
from html import escape
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
import config
from services.stats import XrayStatsService
from datetime import datetime, timezone

stats_service = XrayStatsService()
router = Router()

# Инициализация VLESS менеджера (только нужные параметры)
vless_manager = VLESSManager(
    panel_url=config.XUI_PANEL_URL,
    username=config.XUI_USERNAME,
    password=config.XUI_PASSWORD,
    web_base_path=config.XUI_WEB_BASE_PATH
)


class Payment(StatesGroup):
    waiting_for_payment = State()
    paid = State()


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    """Команда /start - регистрация или вход"""
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    db: Session = get_db_session()
    try:
        existing_client = db.query(Client).filter(
            Client.telegram_id == str(user_id)
        ).first()

        if existing_client:
            await show_main_menu(message, existing_client)
        else:
            # Создаем клиента БЕЗ поля username (его нет в БД)
            new_client = Client(
                telegram_id=str(user_id),
                full_name=full_name,
                login=None,
                subscription_link=None,
                notes=None,
                is_active=False
            )
            db.add(new_client)
            db.commit()
            db.refresh(new_client)

            text = (
                f"👋 <b>Добро пожаловать, {escape(full_name or 'пользователь')}!</b>\n\n"
                f"Я бот для предоставления VPN доступа.\n\n"
                f"<b>Как это работает:</b>\n"
                f"1️⃣ Нажмите <b>'💳 Оплатить подписку'</b>\n"
                f"2️⃣ Выберите тариф и оплатите\n"
                f"3️⃣ После оплаты получите VPN ссылку\n"
                f"4️⃣ Подключайтесь через Hiddify или Happ\n\n"
                f"<b>Тарифы:</b>\n"
                f"💰 300₽/месяц\n"
                f"💰 800₽/3 месяца (выгода 100₽)\n"
                f"💰 3000₽/год (выгода 600₽)\n\n"
                f"Выберите действие ниже 👇"
            )

            await message.answer(text, reply_markup=inline.main_menu_keyboard())

            for admin_id in config.ADMIN_IDS:
                try:
                    await message.bot.send_message(
                        admin_id,
                        f"🔔 <b>Новый клиент!</b>\n\n"
                        f"<b>ID:</b><code>{new_client.id}</code>\n"
                        f"<b>Имя:</b>{escape(full_name or 'Не указано')}\n"
                        f"<b>Username:</b>@{username or 'Не указан'}\n"
                        f"<b>Telegram ID:</b><code>{user_id}</code>\n\n"
                        f"<i>Ожидает оплату...</i>",
                        parse_mode="HTML"
                    )
                except:
                    pass
    finally:
        db.close()


async def show_main_menu(message: types.Message, client_obj: Client):
    status_text = "✅ Активна" if client_obj.is_active else "❌ Не оплачена"
    text = (
        f"👋 <b>С возвращением, {escape(client_obj.full_name or 'пользователь')}!</b>\n\n"
        f"<b>Статус подписки:</b> {status_text}\n"
        f"<b>ID клиента:</b><code>{client_obj.id}</code>\n\n"
        f"Выберите действие:"
    )
    await message.answer(text, reply_markup=inline.main_menu_keyboard())


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    db: Session = get_db_session()
    try:
        client_obj = db.query(Client).filter(Client.telegram_id == str(user_id)).first()
        if client_obj:
            status_text = "✅ Активна" if client_obj.is_active else "❌ Не оплачена"
            text = (
                f"👋 <b>С возвращением, {callback.from_user.full_name or 'пользователь'}!</b>\n\n"
                f"<b>Статус подписки:</b> {status_text}\n"
                f"<b>ID клиента:</b><code>{client_obj.id}</code>\n\n"
                f"Выберите действие:"
            )
        else:
            text = "👋 <b>Добро пожаловать!</b>\n\nНажмите <b>'💳 Оплатить подписку'</b> чтобы начать"

        await callback.message.edit_text(text, reply_markup=inline.main_menu_keyboard(), parse_mode="HTML")
    finally:
        db.close()
    await callback.answer()


@router.callback_query(F.data == "pay_subscription")
async def cb_pay_subscription(callback: CallbackQuery):
    text = (
        "💳 Выберите тариф:\n\n"
        "1 месяц — 300₽\n"
        "📅 3 месяца — 800₽ (выгода 100₽)\n"
        "📅 12 месяцев — 3000₽ (выгода 600₽)\n\n"
        "После оплаты вы получите VPN ссылку."
    )
    await callback.message.edit_text(text, reply_markup=inline.payment_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("pay_"))
async def cb_process_payment(callback: CallbackQuery, state: FSMContext):
    tariff_names = {"pay_300": "1 месяц", "pay_800": "3 месяца", "pay_3000": "12 месяцев"}
    tariff_name = tariff_names.get(callback.data, "Тариф")

    text = (
        f"💳 <b>Оплата: {tariff_name}</b>\n\n"
        f"📱 Карта: 0000 0000 0000 0000\n"
        f"👤 Получатель: ИП Иванов И.И.\n\n"
        f"<i>⚠️ В тестовом режиме нажмите '✅ Я оплатил' ниже</i>"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Я оплатил (тест)", callback_data="confirm_payment_test")
    builder.button(text="❌ Отмена", callback_data="main_menu")

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await state.set_state(Payment.waiting_for_payment)
    await callback.answer()


@router.callback_query(F.data == "confirm_payment_test")
async def cb_confirm_payment_test(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    db: Session = get_db_session()
    try:
        client_obj = db.query(Client).filter(Client.telegram_id == str(user_id)).first()
        if not client_obj:
            await callback.message.answer("❌ Ошибка. Нажмите /start")
            return

        client_obj.is_active = True

        # Генерация email и добавление в Xray
        user_part = client_obj.login or str(user_id)
        email_addr = f"client_{client_obj.id}_{user_part}"

        client_uuid, vless_link = vless_manager.add_client_to_xray(
            client_id=client_obj.id,
            full_name=client_obj.full_name or f"User_{user_id}",
            email=email_addr
        )

        # Сохраняем ссылку в правильное поле (subscription_link)
        client_obj.subscription_link = vless_link
        if not client_obj.login:
            client_obj.login = f"user_{client_obj.id}"
        db.commit()

        await callback.message.answer(
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"🔗 <b>Ваша VPN ссылка:</b>\n<code>{escape(vless_link)}</code>\n\n"
            f"📱 Скопируйте и вставьте в Hiddify/Happ.",
            reply_markup=inline.vpn_ready_keyboard()
        )
        await state.clear()
    finally:
        db.close()
    await callback.answer()


@router.callback_query(F.data == "get_vpn")
async def cb_get_vpn(callback: CallbackQuery):
    user_id = callback.from_user.id
    db: Session = get_db_session()
    try:
        client_obj = db.query(Client).filter(Client.telegram_id == str(user_id)).first()
        if not client_obj:
            await callback.message.answer("❌ Вы не зарегистрированы.")
            return
        if not client_obj.is_active:
            await callback.message.answer("❌ Подписка не оплачена.", reply_markup=inline.back_to_menu_keyboard())
            return
        if not client_obj.subscription_link:
            await callback.message.answer("❌ Ссылка не найдена.")
            return

        await callback.message.answer(
            f"🔗 <b>Ваша ссылка:</b>\n<code>{escape(client_obj.subscription_link)}</code>"
        )
    finally:
        db.close()
    await callback.answer()


@router.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    db: Session = get_db_session()
    try:
        client_obj = db.query(Client).filter(Client.telegram_id == str(user_id)).first()
        if not client_obj:
            await callback.message.answer("❌ Вы не зарегистрированы.")
            return

        status = "✅ Активна" if client_obj.is_active else "❌ Не оплачена"
        text = (
            f"👤 <b>Профиль</b>\n\n"
            f"<b>ID:</b> <code>{client_obj.id}</code>\n"
            f"<b>Имя:</b> {escape(client_obj.full_name or '-')}\n"
            f"<b>Статус:</b> {status}\n"
            f"<b>Дата:</b> {client_obj.created_at.strftime('%d.%m.%Y')}"
        )
        await callback.message.edit_text(text, reply_markup=inline.profile_menu_keyboard(user_id in config.ADMIN_IDS),
                                         parse_mode="HTML")
    finally:
        db.close()
    await callback.answer()


@router.callback_query(F.data == "my_stats")
async def cb_my_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    db: Session = get_db_session()
    try:
        client_obj = db.query(Client).filter(Client.telegram_id == str(user_id)).first()
        if not client_obj:
            await callback.message.answer("❌ Вы не зарегистрированы.")
            return

        # Безопасное обращение к полям, которых может не быть в старой БД
        is_online = getattr(client_obj, 'is_online', False)
        traffic_up = getattr(client_obj, 'traffic_upload', 0) or 0
        traffic_down = getattr(client_obj, 'traffic_download', 0) or 0

        text = (
            f"📊 <b>Статистика</b>\n\n"
            f"<b>Статус:</b> {'🟢 Онлайн' if is_online else '🔴 Офлайн'}\n"
            f"<b>Трафик:</b> ⬇️ {stats_service.format_bytes(traffic_down)} | ⬆️ {stats_service.format_bytes(traffic_up)}"
        )
        await callback.message.answer(text, reply_markup=inline.back_to_menu_keyboard(), parse_mode="HTML")
    finally:
        db.close()
    await callback.answer()


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    await callback.message.answer("❓ Помощь:\n1. Оплата -> 2. Ссылка -> 3. Подключение.\nПриложения: Hiddify, Happ.",
                                  reply_markup=inline.back_to_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "cancel_payment")
async def cb_cancel_payment(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено.", reply_markup=inline.back_to_menu_keyboard())
    await callback.answer()