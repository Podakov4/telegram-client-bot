#!/usr/bin/env python3
"""Telegram Client Bot - Main Entry Point"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
from database import create_tables
from handlers import admin, client, common, documents, inline_referral, instructions, menu, news, support

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("🚀 Запуск бота...")
    await create_tables()
    logger.info("✅ База данных готова")

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(common.router)
    dp.include_router(client.router)
    dp.include_router(menu.router)
    dp.include_router(admin.router)
    dp.include_router(instructions.router)
    dp.include_router(support.router)
    dp.include_router(documents.router)
    dp.include_router(news.router)
    dp.include_router(inline_referral.router)

    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("✅ Бот запущен и готов к работе!")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("🔌 Сессия бота закрыта")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")