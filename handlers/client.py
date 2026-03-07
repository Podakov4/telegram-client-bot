# handlers/client.py
from aiogram import types, Router, F
from aiogram.filters import Command
from sqlalchemy.orm import Session
from database import get_db_session, Client
from html import escape
import config

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
    """Статистика"""
    user_id = message.from_user.id

    if user_id not in config.ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к этой команде.")
        return

    db: Session = get_db_session()
    try:
        total = db.query(Client).count()
        active = db.query(Client).filter(Client.is_active == True).count()
        with_vpn = db.query(Client).filter(Client.wireguard_config != None).count()

        text = (
            f"📊 <b>Статистика</b>\n\n"
            f"<b>Всего клиентов:</b> {total}\n"
            f"<b>Активных (оплатили):</b> {active}\n"
            f"<b>С VPN:</b> {with_vpn}\n"
            f"<b>Ожидают оплату:</b> {total - active}"
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