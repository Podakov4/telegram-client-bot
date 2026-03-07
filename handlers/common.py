# handlers/common.py
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
from datetime import datetime, timezone

# Инициализация сервиса статистики
stats_service = XrayStatsService()

router = Router()

# Инициализация VLESS менеджера
vless_manager = VLESSManager(
    server_ip=config.WG_SERVER_IP,
    port=config.VLESS_PORT,
    path=config.VLESS_PATH if hasattr(config, 'VLESS_PATH') else "/vless",
    host="freeth.ru"
)


# Машина состояний для оплаты
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
        # Проверка - есть ли уже клиент в БД
        existing_client = db.query(Client).filter(
            Client.telegram_id == str(user_id)
        ).first()

        if existing_client:
            # Клиент уже зарегистрирован
            await show_main_menu(message, existing_client)
        else:
            # Новый клиент - регистрируем
            new_client = Client(
                telegram_id=str(user_id),
                username=username,
                full_name=full_name,
                phone=None,
                email=None,
                notes=None,
                is_active=False  # Пока не активен до оплаты
            )
            db.add(new_client)
            db.commit()
            db.refresh(new_client)

            # Приветственное сообщение с меню
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

            await message.answer(
                text,
                reply_markup=inline.main_menu_keyboard()
            )

            # Уведомление админу о новом клиенте
            for admin_id in config.ADMIN_IDS:
                try:
                    await message.bot.send_message(
                        admin_id,
                        f"🔔 <b>Новый клиент!</b>\n\n"
                        f"<b>ID:</b> <code>{new_client.id}</code>\n"
                        f"<b>Имя:</b> {escape(full_name or 'Не указано')}\n"
                        f"<b>Username:</b> @{username or 'Не указан'}\n"
                        f"<b>Telegram ID:</b> <code>{user_id}</code>\n\n"
                        f"<i>Ожидает оплату...</i>"
                    )
                except:
                    pass

    finally:
        db.close()


async def show_main_menu(message: types.Message, client: Client):
    """Показать главное меню"""
    status_text = "✅ Активна" if client.is_active else "❌ Не оплачена"

    text = (
        f"👋 <b>С возвращением, {escape(client.full_name or 'пользователь')}!</b>\n\n"
        f"<b>Статус подписки:</b> {status_text}\n"
        f"<b>ID клиента:</b> <code>{client.id}</code>\n\n"
        f"Выберите действие:"
    )

    await message.answer(
        text,
        reply_markup=inline.main_menu_keyboard()
    )



@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    """Кнопка главное меню (аналог /start)"""
    await state.clear()

    user_id = callback.from_user.id
    username = callback.from_user.username
    full_name = callback.from_user.full_name

    db: Session = get_db_session()
    try:
        client = db.query(Client).filter(
            Client.telegram_id == str(user_id)
        ).first()

        if client:
            # Клиент зарегистрирован
            status_text = "✅ Активна" if client.is_active else "❌ Не оплачена"

            text = (
                f"👋 <b>С возвращением, {escape(full_name or 'пользователь')}!</b>\n\n"
                f"<b>Статус подписки:</b> {status_text}\n"
                f"<b>ID клиента:</b> <code>{client.id}</code>\n\n"
                f"Выберите действие:"
            )
        else:
            # Новый клиент
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

        await callback.message.edit_text(
            text,
            reply_markup=inline.main_menu_keyboard(),
            parse_mode="HTML"
        )

    finally:
        db.close()

    await callback.answer()


@router.callback_query(F.data == "pay_subscription")
async def cb_pay_subscription(callback: CallbackQuery):
    """Показать тарифы"""
    text = (
        "💳 <b>Выберите тариф:</b>\n\n"
        f"<b> 1 месяц</b> — 300₽\n"
        f"<b>📅 3 месяца</b> — 800₽ <i>(выгода 100₽)</i>\n"
        f"<b>📅 12 месяцев</b> — 3000₽ <i>(выгода 600₽)</i>\n\n"
        f"<i>После оплаты вы получите VPN ссылку для подключения</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=inline.payment_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_"))
async def cb_process_payment(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора тарифа"""
    tariff = callback.data

    tariff_names = {
        "pay_300": "1 месяц (300₽)",
        "pay_800": "3 месяца (800₽)",
        "pay_3000": "12 месяцев (3000₽)"
    }

    tariff_name = tariff_names.get(tariff, "Неизвестный тариф")

    # TODO: Здесь будет интеграция с платежной системой
    # Пока что просто имитируем оплату

    text = (
        f"💳 <b>Оплата: {tariff_name}</b>\n\n"
        f"<b>Реквизиты для оплаты:</b>\n"
        f"📱 Карта: 0000 0000 0000 0000\n"
        f"👤 Получатель: ИП Иванов И.И.\n\n"
        f"<b>Инструкция:</b>\n"
        f"1. Переведите сумму на карту\n"
        f"2. Отправьте чек в поддержку\n"
        f"3. После проверки вы получите VPN доступ\n\n"
        f"<i>⚠️ В тестовом режиме нажмите '✅ Я оплатил' ниже</i>"
    )

    # Кнопка для теста (потом удалим)
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Я оплатил (тест)", callback_data="confirm_payment_test")
    builder.button(text="❌ Отмена", callback_data="main_menu")

    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup()
    )

    await state.set_state(Payment.waiting_for_payment)
    await callback.answer()


@router.callback_query(F.data == "confirm_payment_test")
async def cb_confirm_payment_test(callback: CallbackQuery, state: FSMContext):
    """Тестовое подтверждение оплаты"""
    user_id = callback.from_user.id

    db: Session = get_db_session()
    try:
        client = db.query(Client).filter(
            Client.telegram_id == str(user_id)
        ).first()

        if not client:
            await callback.message.answer("❌ Ошибка. Нажмите /start")
            return

        # Активируем клиента
        client.is_active = True

        # 🔥 Генерация VLESS ссылки и добавление в Xray
        client_uuid, vless_link = vless_manager.add_client_to_xray(
            client_id=client.id,
            full_name=client.full_name or f"User_{user_id}",
            email=f"client_{client.id}_{client.username or user_id}"
        )

        # Сохранение VLESS конфигурации
        client.wireguard_public_key = client_uuid
        client.wireguard_config = vless_link
        db.commit()

        # 🔥 Отправляем ссылку с кнопкой копирования
        await callback.message.answer(
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"Ваша подписка активирована.\n\n"
            f"🔗 <b>Ваша VPN ссылка (VLESS):</b>\n"
            f"<code>{escape(vless_link)}</code>\n\n"
            f"📱 <b>Для подключения:</b>\n"
            f"1. Нажмите <b>'📋 Копировать ссылку'</b> ниже\n"
            f"2. Откройте Hiddify или Happ\n"
            f"3. Вставьте ссылку и подключайтесь!\n\n"
            f"<i>Ссылку всегда можно получить через меню</i>",
            reply_markup=inline.vpn_ready_keyboard()
        )

        await state.clear()

        # Уведомление админу
        for admin_id in config.ADMIN_IDS:
            try:
                await callback.message.bot.send_message(
                    admin_id,
                    f"💰 <b>Новая оплата!</b>\n\n"
                    f"<b>Клиент:</b> {escape(client.full_name or 'Не указано')}\n"
                    f"<b>ID:</b> <code>{client.id}</code>\n"
                    f"<b>Telegram:</b> @{escape(client.username or 'не указан')}\n"
                    f"<b>UUID:</b> <code>{client_uuid}</code>"
                )
            except:
                pass

    finally:
        db.close()

    await callback.answer()


@router.callback_query(F.data == "get_vpn")
async def cb_get_vpn(callback: CallbackQuery):
    """Получить VPN ссылку"""
    user_id = callback.from_user.id

    db: Session = get_db_session()
    try:
        client = db.query(Client).filter(
            Client.telegram_id == str(user_id)
        ).first()

        if not client:
            await callback.message.answer("❌ Вы не зарегистрированы. Нажмите /start")
            return

        if not client.is_active:
            text = (
                "❌ <b>Подписка не оплачена</b>\n\n"
                "Для получения доступа к VPN необходимо оплатить подписку.\n\n"
                "Нажмите <b>'💳 Оплатить подписку'</b> в главном меню."
            )
            await callback.message.answer(
                text,
                reply_markup=inline.back_to_menu_keyboard()
            )
            await callback.answer()
            return

        if not client.wireguard_config:
            await callback.message.answer("❌ VPN ссылка не сгенерирована. Обратитесь к администратору.")
            await callback.answer()
            return

        text = (
            f"🔗 <b>Ваша VPN ссылка (VLESS):</b>\n\n"
            f"<code>{escape(client.wireguard_config)}</code>\n\n"
            f"📱 <b>Для подключения:</b>\n"
            f"1. Скачайте <b>Hiddify</b> или <b>Happ</b>\n"
            f"2. Нажмите <b>'+'</b> и вставьте ссылку\n"
            f"3. Подключайтесь!"
        )

        await callback.message.answer(text)

    finally:
        db.close()

    await callback.answer()


@router.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery):
    """Показать профиль с кнопками"""
    user_id = callback.from_user.id

    db: Session = get_db_session()
    try:
        client = db.query(Client).filter(
            Client.telegram_id == str(user_id)
        ).first()

        if not client:
            await callback.message.answer("❌ Вы не зарегистрированы. Нажмите /start")
            return

        # Проверяем админ ли
        is_admin = user_id in config.ADMIN_IDS

        status = "✅ Активна" if client.is_active else "❌ Не оплачена"

        text = (
            f"👤 <b>Ваш профиль</b>\n\n"
            f"<b>ID клиента:</b> <code>{client.id}</code>\n"
            f"<b>Имя:</b> {escape(client.full_name or 'Не указано')}\n"
            f"<b>Telegram:</b> @{escape(client.username or 'не указан')}\n"
            f"<b>Статус подписки:</b> {status}\n"
            f"<b>Дата регистрации:</b> {client.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Выберите действие:"
        )

        await callback.message.edit_text(
            text,
            reply_markup=inline.profile_menu_keyboard(is_admin),
            parse_mode="HTML"
        )

    finally:
        db.close()

    await callback.answer()


@router.callback_query(F.data == "my_stats")
async def cb_my_stats(callback: CallbackQuery):
    """Личная статистика пользователя"""
    user_id = callback.from_user.id

    db: Session = get_db_session()
    try:
        client = db.query(Client).filter(
            Client.telegram_id == str(user_id)
        ).first()

        if not client:
            await callback.message.answer("❌ Вы не зарегистрированы. Нажмите /start")
            return

        # Определяем статус онлайн
        is_online = stats_service.is_client_online(client.last_seen)

        # Обновляем last_seen при запросе
        client.last_seen = datetime.now(timezone.utc)
        client.is_online = is_online
        db.commit()

        # Срок подписки
        if client.subscription_end:
            days_left = (client.subscription_end - datetime.now(timezone.utc)).days
            if days_left > 0:
                subscription_text = f"✅ Активна ({days_left} дн. осталось)"
            else:
                subscription_text = "❌ Истекла"
        else:
            subscription_text = "✅ Активна" if client.is_active else "❌ Не оплачена"

        text = (
            f"📊 <b>Ваша статистика</b>\n\n"
            f"<b>Статус подписки:</b> {subscription_text}\n"
            f"<b>Статус подключения:</b> {'🟢 Онлайн' if is_online else '🔴 Офлайн'}\n"
            f"<b>Последняя активность:</b> {client.last_seen.strftime('%d.%m.%Y %H:%M') if client.last_seen else 'Никогда'}\n\n"
            f"<b>📈 Трафик:</b>\n"
            f"  • ⬆️ Загружено: {stats_service.format_bytes(client.traffic_upload or 0)}\n"
            f"  • ⬇️ Скачано: {stats_service.format_bytes(client.traffic_download or 0)}\n"
            f"  • 🔄 Всего: {stats_service.format_bytes((client.traffic_upload or 0) + (client.traffic_download or 0))}\n\n"
            f"<b>🔗 Подключений:</b> {client.connection_count or 0}\n\n"
            f"<i>Статистика обновляется каждые 5 минут</i>"
        )

        await callback.message.answer(
            text,
            reply_markup=inline.back_to_menu_keyboard(),
            parse_mode="HTML"
        )

    finally:
        db.close()

    await callback.answer()


@router.callback_query(F.data == "server_stats")
async def cb_server_stats(callback: CallbackQuery):
    """Статистика сервера (только админ)"""
    user_id = callback.from_user.id

    if user_id not in config.ADMIN_IDS:
        await callback.message.answer("❌ У вас нет доступа к этой команде.")
        return

    db: Session = get_db_session()
    try:
        total = db.query(Client).count()
        active = db.query(Client).filter(Client.is_active == True).count()
        online = db.query(Client).filter(Client.is_online == True).count()
        with_vpn = db.query(Client).filter(Client.wireguard_config != None).count()

        # Общая статистика трафика
        from sqlalchemy import func
        total_upload = db.query(func.sum(Client.traffic_upload)).scalar() or 0
        total_download = db.query(func.sum(Client.traffic_download)).scalar() or 0

        text = (
            f"📊 <b>Статистика сервера</b>\n\n"
            f"<b>👥 Клиенты:</b>\n"
            f"  • Всего: {total}\n"
            f"  • Активных (оплатили): {active}\n"
            f"  • Онлайн сейчас: {online}\n"
            f"  • С VPN: {with_vpn}\n\n"
            f"<b>📈 Трафик:</b>\n"
            f"  • ⬆️ Загружено: {stats_service.format_bytes(total_upload)}\n"
            f"  • ⬇️ Скачано: {stats_service.format_bytes(total_download)}\n"
            f"  • 🔄 Всего: {stats_service.format_bytes(total_upload + total_download)}"
        )

        await callback.message.answer(
            text,
            reply_markup=inline.admin_stats_keyboard(),
            parse_mode="HTML"
        )

    finally:
        db.close()

    await callback.answer()

@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    """Помощь"""
    text = (
        "❓ <b>Помощь</b>\n\n"
        "<b>Как получить VPN:</b>\n"
        "1. Нажмите <b>'💳 Оплатить подписку'</b>\n"
        "2. Выберите тариф\n"
        "3. Оплатите\n"
        "4. Получите VPN ссылку\n\n"
        "<b>Приложения для подключения:</b>\n"
        "📱 <b>Hiddify</b> (iOS/Android)\n"
        "📱 <b>Happ</b> (Android)\n\n"
        "По всем вопросам обращайтесь к администратору."
    )

    await callback.message.answer(
        text,
        reply_markup=inline.back_to_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_payment")
async def cb_cancel_payment(callback: CallbackQuery, state: FSMContext):
    """Отмена оплаты"""
    await state.clear()
    text = "❌ Оплата отменена.\n\nВыберите действие в главном меню."
    await callback.message.edit_text(
        text,
        reply_markup=inline.back_to_menu_keyboard()
    )
    await callback.answer()


@router.message(Command("my_stats"))
async def cmd_my_stats(message: types.Message):
    """Личная статистика пользователя"""
    user_id = message.from_user.id

    db: Session = get_db_session()
    try:
        client = db.query(Client).filter(
            Client.telegram_id == str(user_id)
        ).first()

        if not client:
            await message.answer("❌ Вы не зарегистрированы. Нажмите /start")
            return

        # Определяем статус онлайн
        is_online = stats_service.is_client_online(client.last_seen)

        # Обновляем last_seen при запросе
        client.last_seen = datetime.now(timezone.utc)
        client.is_online = is_online
        db.commit()

        # Срок подписки
        if client.subscription_end:
            days_left = (client.subscription_end - datetime.now(timezone.utc)).days
            if days_left > 0:
                subscription_text = f"✅ Активна ({days_left} дн. осталось)"
            else:
                subscription_text = "❌ Истекла"
        else:
            subscription_text = "✅ Активна" if client.is_active else "❌ Не оплачена"

        text = (
            f"📊 <b>Ваша статистика</b>\n\n"
            f"<b>Статус подписки:</b> {subscription_text}\n"
            f"<b>Статус подключения:</b> {'🟢 Онлайн' if is_online else '🔴 Офлайн'}\n"
            f"<b>Последняя активность:</b> {client.last_seen.strftime('%d.%m.%Y %H:%M') if client.last_seen else 'Никогда'}\n\n"
            f"<b>📈 Трафик:</b>\n"
            f"  • ⬆️ Загружено: {stats_service.format_bytes(client.traffic_upload or 0)}\n"
            f"  • ⬇️ Скачано: {stats_service.format_bytes(client.traffic_download or 0)}\n"
            f"  • 🔄 Всего: {stats_service.format_bytes((client.traffic_upload or 0) + (client.traffic_download or 0))}\n\n"
            f"<b>🔗 Подключений:</b> {client.connection_count or 0}\n\n"
            f"<i>Статистика обновляется каждые 5 минут</i>"
        )

        await message.answer(text)

    finally:
        db.close()


@router.callback_query(F.data.startswith("copy_vpn:"))
async def cb_copy_vpn(callback: CallbackQuery):
    """Копирование VPN ссылки"""
    user_id = callback.from_user.id

    # Извлекаем ссылку из callback_data
    vpn_link = callback.data.replace("copy_vpn:", "")

    db: Session = get_db_session()
    try:
        client = db.query(Client).filter(
            Client.telegram_id == str(user_id)
        ).first()

        if not client or not client.is_active or not client.wireguard_config:
            await callback.message.answer("❌ У вас нет активной VPN ссылки")
            await callback.answer()
            return

        # 🔥 Отправляем ссылку отдельным сообщением - её можно скопировать!
        await callback.message.answer(
            f"<code>{escape(vpn_link)}</code>",
            parse_mode="HTML"
        )

        await callback.answer("✅ Ссылка отправлена! Нажмите на неё чтобы скопировать", show_alert=True)

    finally:
        db.close()


@router.callback_query(F.data == "copy_vpn_now")
async def cb_copy_vpn_now(callback: CallbackQuery):
    """Копирование VPN ссылки (после оплаты)"""
    user_id = callback.from_user.id

    db: Session = get_db_session()
    try:
        client = db.query(Client).filter(
            Client.telegram_id == str(user_id)
        ).first()

        if not client or not client.wireguard_config:
            await callback.message.answer("❌ VPN ссылка недоступна")
            await callback.answer()
            return

        # 🔥 Отправляем ссылку отдельным сообщением
        await callback.message.answer(
            f"<code>{escape(client.wireguard_config)}</code>",
            parse_mode="HTML"
        )

        await callback.answer("✅ Ссылка отправлена! Нажмите на неё чтобы скопировать", show_alert=True)

    finally:
        db.close()


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
            # Клиент уже зарегистрирован - покажи меню с кнопками
            status_text = "✅ Активна" if existing_client.is_active else "❌ Не оплачена"

            text = (
                f"👋 <b>С возвращением, {escape(full_name or 'пользователь')}!</b>\n\n"
                f"<b>Статус подписки:</b> {status_text}\n"
                f"<b>ID клиента:</b> <code>{existing_client.id}</code>\n\n"
                f"Выберите действие:"
            )

            await message.answer(
                text,
                reply_markup=inline.main_menu_keyboard(),
                parse_mode="HTML"
            )
        else:
            # Новый клиент - регистрируем
            new_client = Client(
                telegram_id=str(user_id),
                username=username,
                full_name=full_name,
                phone=None,
                email=None,
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

            await message.answer(
                text,
                reply_markup=inline.main_menu_keyboard(),
                parse_mode="HTML"
            )

            # Уведомление админу
            for admin_id in config.ADMIN_IDS:
                try:
                    await message.bot.send_message(
                        admin_id,
                        f"🔔 <b>Новый клиент!</b>\n\n"
                        f"<b>ID:</b> <code>{new_client.id}</code>\n"
                        f"<b>Имя:</b> {escape(full_name or 'Не указано')}\n"
                        f"<b>Username:</b> @{username or 'Не указан'}\n"
                        f"<b>Telegram ID:</b> <code>{user_id}</code>\n\n"
                        f"<i>Ожидает оплату...</i>",
                        parse_mode="HTML"
                    )
                except:
                    pass

    finally:
        db.close()