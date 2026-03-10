import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from services.subscriptions import get_expiring_clients

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def renewal_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Продлить подписку", callback_data="open_payment_menu")
    builder.adjust(1)
    return builder.as_markup()


async def main():
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    clients = await get_expiring_clients(days=3)

    if not clients:
        logger.info("Нет подписок, истекающих в ближайшие 3 дня.")
        await bot.session.close()
        return

    sent_count = 0

    for client in clients:
        try:
            paid_until = (
                client.paid_until.strftime("%Y-%m-%d %H:%M")
                if client.paid_until
                else "скоро"
            )

            text = (
                f"Здравствуйте, {client.full_name or 'пользователь'}!\n\n"
                f"Ваша подписка истекает: {paid_until}\n\n"
                "Чтобы не потерять доступ, продлите подписку заранее."
            )

            await bot.send_message(
                chat_id=int(client.telegram_id),
                text=text,
                reply_markup=renewal_keyboard(),
            )
            sent_count += 1
            logger.info("Напоминание отправлено telegram_id=%s", client.telegram_id)

        except Exception as e:
            logger.exception(
                "Не удалось отправить напоминание telegram_id=%s: %s",
                client.telegram_id,
                e,
            )

    logger.info("Готово. Отправлено напоминаний: %s", sent_count)
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())