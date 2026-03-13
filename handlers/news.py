from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from config import ADMIN_IDS
from database.db import AsyncSessionLocal
from database.models import Client

router = Router()


class NewsStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_confirm = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def news_preview_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Отправить всем", callback_data="news_send_all")
    builder.button(text="Отправить активным", callback_data="news_send_active")
    builder.button(text="Отмена", callback_data="news_cancel")
    builder.adjust(1)
    return builder.as_markup()


@router.message(Command("news"))
async def cmd_news(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("Недостаточно прав.")
        return

    await state.set_state(NewsStates.waiting_for_text)
    await message.answer(
        "Отправьте текст новости одним сообщением.\n\n"
        "Поддерживается обычный текст и HTML-разметка Telegram.\n"
        "Для отмены введите /cancel_news"
    )


@router.message(Command("cancel_news"))
async def cancel_news_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Создание новости отменено.")


@router.message(NewsStates.waiting_for_text)
async def news_text_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("Недостаточно прав.")
        return

    text = (message.html_text or "").strip()
    if not text:
        await message.answer("Нужен текст новости.")
        return

    await state.update_data(news_text=text)
    await state.set_state(NewsStates.waiting_for_confirm)

    await message.answer(
        "Предпросмотр новости:\n\n" + text,
        reply_markup=news_preview_keyboard(),
    )


async def get_news_recipients(active_only: bool) -> list[Client]:
    async with AsyncSessionLocal() as session:
        stmt = select(Client)
        if active_only:
            stmt = stmt.where(Client.is_active == True)

        result = await session.execute(stmt.order_by(Client.id.asc()))
        return list(result.scalars().all())


async def send_news(bot: Bot, text: str, active_only: bool) -> tuple[int, int]:
    clients = await get_news_recipients(active_only=active_only)

    sent = 0
    failed = 0

    for client in clients:
        try:
            await bot.send_message(
                chat_id=int(client.telegram_id),
                text=text,
            )
            sent += 1
        except Exception:
            failed += 1

    return sent, failed


@router.callback_query(F.data == "news_send_all", NewsStates.waiting_for_confirm)
async def news_send_all(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    data = await state.get_data()
    text = data.get("news_text", "").strip()

    if not text:
        await callback.message.answer("Текст новости не найден. Начните заново: /news")
        await state.clear()
        await callback.answer()
        return

    sent, failed = await send_news(bot, text=text, active_only=False)
    await state.clear()

    await callback.message.answer(
        f"Готово.\n\n"
        f"Отправлено всем: {sent}\n"
        f"Ошибок: {failed}"
    )
    await callback.answer("Рассылка завершена")


@router.callback_query(F.data == "news_send_active", NewsStates.waiting_for_confirm)
async def news_send_active(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    data = await state.get_data()
    text = data.get("news_text", "").strip()

    if not text:
        await callback.message.answer("Текст новости не найден. Начните заново: /news")
        await state.clear()
        await callback.answer()
        return

    sent, failed = await send_news(bot, text=text, active_only=True)
    await state.clear()

    await callback.message.answer(
        f"Готово.\n\n"
        f"Отправлено активным: {sent}\n"
        f"Ошибок: {failed}"
    )
    await callback.answer("Рассылка завершена")


@router.callback_query(F.data == "news_cancel", NewsStates.waiting_for_confirm)
async def news_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Рассылка отменена.")
    await callback.answer("Отменено")