from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
import logging

from config import ADMIN_IDS
from database.db import AsyncSessionLocal
from database.models import Client

router = Router()
logger = logging.getLogger(__name__)


class NewsStates(StatesGroup):
    waiting_for_content = State()
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

    await state.set_state(NewsStates.waiting_for_content)
    await message.answer(
        "Отправьте новость одним сообщением.\n\n"
        "Можно:\n"
        "• только текст\n"
        "• фото с подписью\n\n"
        "Для отмены введите /cancel_news"
    )


@router.message(Command("cancel_news"))
async def cancel_news_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Создание новости отменено.")


@router.message(NewsStates.waiting_for_content, F.photo)
async def news_photo_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("Недостаточно прав.")
        return

    photo = message.photo[-1]
    caption = (message.html_text or "").strip()

    await state.update_data(
        news_type="photo",
        news_file_id=photo.file_id,
        news_text=caption,
    )
    await state.set_state(NewsStates.waiting_for_confirm)

    await message.answer_photo(
        photo.file_id,
        caption=caption or "Предпросмотр новости без подписи",
        reply_markup=news_preview_keyboard(),
    )


@router.message(NewsStates.waiting_for_content)
async def news_text_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("Недостаточно прав.")
        return

    text = (message.html_text or "").strip()
    if not text:
        await message.answer("Нужен текст новости или фото с подписью.")
        return

    await state.update_data(
        news_type="text",
        news_text=text,
    )
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


async def send_news(bot: Bot, data: dict, active_only: bool) -> tuple[int, int, list[str]]:
    clients = await get_news_recipients(active_only=active_only)

    sent = 0
    failed = 0
    failed_ids: list[str] = []

    news_type = data.get("news_type")
    news_text = data.get("news_text", "")
    news_file_id = data.get("news_file_id")

    for client in clients:
        try:
            if news_type == "photo" and news_file_id:
                await bot.send_photo(
                    chat_id=int(client.telegram_id),
                    photo=news_file_id,
                    caption=news_text or None,
                )
            else:
                await bot.send_message(
                    chat_id=int(client.telegram_id),
                    text=news_text,
                )
            sent += 1
        except Exception as e:
            failed += 1
            failed_ids.append(str(client.telegram_id))
            logger.exception(
                "Не удалось отправить новость telegram_id=%s: %s",
                client.telegram_id,
                e,
            )

    return sent, failed, failed_ids


def build_failed_ids_text(failed_ids: list[str]) -> str:
    if not failed_ids:
        return ""

    preview = "\n".join(failed_ids[:20])
    extra = ""
    if len(failed_ids) > 20:
        extra = f"\n\nИ ещё: {len(failed_ids) - 20}"

    return f"\n\nНе доставлено telegram_id:\n{preview}{extra}"


@router.callback_query(F.data == "news_send_all", NewsStates.waiting_for_confirm)
async def news_send_all(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    data = await state.get_data()
    if not data:
        await callback.message.answer("Новость не найдена. Начните заново: /news")
        await state.clear()
        await callback.answer()
        return

    sent, failed, failed_ids = await send_news(bot, data=data, active_only=False)
    await state.clear()

    await callback.message.answer(
        f"Готово.\n\n"
        f"Отправлено всем: {sent}\n"
        f"Ошибок: {failed}"
        f"{build_failed_ids_text(failed_ids)}"
    )
    await callback.answer("Рассылка завершена")


@router.callback_query(F.data == "news_send_active", NewsStates.waiting_for_confirm)
async def news_send_active(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    data = await state.get_data()
    if not data:
        await callback.message.answer("Новость не найдена. Начните заново: /news")
        await state.clear()
        await callback.answer()
        return

    sent, failed, failed_ids = await send_news(bot, data=data, active_only=True)
    await state.clear()

    await callback.message.answer(
        f"Готово.\n\n"
        f"Отправлено активным: {sent}\n"
        f"Ошибок: {failed}"
        f"{build_failed_ids_text(failed_ids)}"
    )
    await callback.answer("Рассылка завершена")


@router.callback_query(F.data == "news_cancel", NewsStates.waiting_for_confirm)
async def news_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Рассылка отменена.")
    await callback.answer("Отменено")