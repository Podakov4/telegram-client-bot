from aiogram import Bot, Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Client

router = Router()


def build_referral_link(bot_username: str, referral_code: str) -> str:
    return f"https://t.me/{bot_username}?start=ref_{referral_code}"


@router.inline_query()
async def inline_referral_share(inline_query: InlineQuery, bot: Bot):
    query = (inline_query.query or "").strip().lower()

    if query and not query.startswith("share_referral"):
        await inline_query.answer([], cache_time=1, is_personal=True)
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == str(inline_query.from_user.id))
        )
        client = result.scalar_one_or_none()

    if client is None:
        await inline_query.answer([], cache_time=1, is_personal=True)
        return

    referral_code = getattr(client, "referral_code", None)
    if not referral_code:
        await inline_query.answer([], cache_time=1, is_personal=True)
        return

    me = await bot.get_me()
    referral_link = build_referral_link(me.username, referral_code)

    message_text = (
        "<b>Freeth</b>\n\n"
        "Freeth — это удобный сервис для защищенного и стабильного подключения. "
        "Подходит для быстрого доступа, приватного соединения и повседневного использования без лишних настроек.\n\n"
        "Подключение занимает всего пару минут:\n"
        "• открой бота\n"
        "• активируй доступ\n"
        "• подключись по готовой инструкции\n\n"
        f"{referral_link}"
    )

    result = InlineQueryResultArticle(
        id=f"referral_{inline_query.from_user.id}",
        title="Отправить ссылку другу",
        description="Поделиться ссылкой на Freeth",
        input_message_content=InputTextMessageContent(
            message_text=message_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        ),
    )

    await inline_query.answer([result], cache_time=1, is_personal=True)
