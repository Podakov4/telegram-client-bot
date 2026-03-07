# handlers/client.py
from aiogram import types, Router, F
from aiogram.filters import Command
from sqlalchemy.orm import Session
from database import get_db_session, Client
from html import escape
import config
from services.stats import XrayStatsService
from datetime import datetime, timezone
from sqlalchemy import func

# Инициализация сервиса статистики
stats_service = XrayStatsService()

router = Router()


@router.message(Command("clients"))
async def cmd_clients(message: types.Message):
    """Показать всех клиентов (только админ)"""
    user_id = message.from_user.id

    if user_id not in config.ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к этой команде.")
        return

    db: Session = get_db_session()
    try:
        clients = db.query(Client).all()

        if not clients:
            await message.answer("📭 Клиентов пока нет.")
            return

        active_count = sum(1 for c in clients if c.is_active)

        text = f"📋 <b>Всего клиентов: {len(clients)}</b>\n"
        text += f"<b>Активных:</b> {active_count}\n\n"

        for client in clients[:20]:
            status = "✅" if client.is_active else "❌"
            vpn = "🔗" if client.wireguard_config else ""

            text += (
                f"{status} <b>#{client.id}</b> {escape(client.full_name or 'Без имени')}\n"
                f"📱 {escape(client.phone) or '—'}\n"
                f"🆔 <code>{client.telegram_id}</code>\n"
                f"{vpn}\n\n"
            )

        if len(clients) > 20:
            text += f"... и ещё {len(clients) - 20} клиентов"

        await message.answer(text)
    finally:
        db.close()


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Общая статистика сервера (только админ)"""
    user_id = message.from_user.id

    if user_id not in config.ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к этой команде.")
        return

    db: Session = get_db_session()
    try:
        total = db.query(Client).count()
        active = db.query(Client).filter(Client.is_active == True).count()
        online = db.query(Client).filter(Client.is_online == True).count()
        with_vpn = db.query(Client).filter(Client.wireguard_config != None).count()

        # Общая статистика трафика
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

        await message.answer(text)

    finally:
        db.close()


@router.message(Command("activate"))
async def cmd_activate(message: types.Message):
    """Активировать клиента вручную (админ)"""
    user_id = message.from_user.id

    if user_id not in config.ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к этой команде.")
        return

    # Формат: /activate 123 (где 123 - ID клиента)
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /activate <client_id>")
        return

    try:
        client_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return

    db: Session = get_db_session()
    try:
        client = db.query(Client).filter(Client.id == client_id).first()

        if not client:
            await message.answer(f"❌ Клиент #{client_id} не найден")
            return

        client.is_active = True
        db.commit()

        await message.answer(f"✅ Клиент #{client_id} активирован!")

        # Уведомление клиенту
        try:
            await message.bot.send_message(
                client.telegram_id,
                "✅ <b>Ваша подписка активирована!</b>\n\n"
                "Теперь вы можете получить VPN ссылку через меню."
            )
        except:
            pass

    finally:
        db.close()


@router.message(Command("client_stats"))
async def cmd_client_stats(message: types.Message):
    """Статистика по конкретному клиенту (только админ)"""
    user_id = message.from_user.id

    if user_id not in config.ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к этой команде.")
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /client_stats <client_id>")
        return

    try:
        client_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return

    db: Session = get_db_session()
    try:
        client = db.query(Client).filter(Client.id == client_id).first()

        if not client:
            await message.answer(f"❌ Клиент #{client_id} не найден")
            return

        # Определяем статус онлайн
        is_online = stats_service.is_client_online(client.last_seen)

        # Обновляем статус в БД
        client.is_online = is_online
        if is_online:
            client.last_seen = datetime.now(timezone.utc)
        db.commit()

        text = (
            f"👤 <b>Статистика клиента #{client.id}</b>\n\n"
            f"<b>Имя:</b> {escape(client.full_name or 'Не указано')}\n"
            f"<b>Telegram:</b> @{escape(client.username or 'не указан')}\n"
            f"<b>Статус:</b> {'🟢 Онлайн' if is_online else '🔴 Офлайн'}\n"
            f"<b>Подписка:</b> {'✅ Активна' if client.is_active else '❌ Не оплачена'}\n"
            f"<b>Последний вход:</b> {client.last_seen.strftime('%d.%m.%Y %H:%M') if client.last_seen else 'Никогда'}\n\n"
            f"<b>📊 Трафик:</b>\n"
            f"  • ⬆️ Загружено: {stats_service.format_bytes(client.traffic_upload or 0)}\n"
            f"  • ⬇️ Скачано: {stats_service.format_bytes(client.traffic_download or 0)}\n"
            f"  • 🔄 Всего: {stats_service.format_bytes((client.traffic_upload or 0) + (client.traffic_download or 0))}\n\n"
            f"<b>🔗 Подключения:</b> {client.connection_count or 0} раз"
        )

        await message.answer(text)

    finally:
        db.close()


@router.message(Command("top_traffic"))
async def cmd_top_traffic(message: types.Message):
    """Топ клиентов по трафику (только админ)"""
    user_id = message.from_user.id

    if user_id not in config.ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к этой команде.")
        return

    db: Session = get_db_session()
    try:
        clients = db.query(Client).filter(
            Client.is_active == True,
            Client.wireguard_config != None
        ).order_by(
            (Client.traffic_upload + Client.traffic_download).desc()
        ).limit(10).all()

        if not clients:
            await message.answer("📭 Нет данных о трафике")
            return

        text = f"🏆 <b>Топ-10 по трафику</b>\n\n"
        for i, client in enumerate(clients, 1):
            total = (client.traffic_upload or 0) + (client.traffic_download or 0)
            text += (
                f"<b>{i}. {escape(client.full_name or f'Клиент #{client.id}')}</b>\n"
                f"   📊 {stats_service.format_bytes(total)}\n"
                f"   ⬆️ {stats_service.format_bytes(client.traffic_upload or 0)} | "
                f"⬇️ {stats_service.format_bytes(client.traffic_download or 0)}\n\n"
            )

        await message.answer(text)

    finally:
        db.close()