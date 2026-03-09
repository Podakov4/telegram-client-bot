#!/usr/bin/env python3
"""Telegram Client Bot - Main Entry Point"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from database import create_tables
from handlers import common, client, menu
import config

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """Основная функция"""
    logger.info("🚀 Запуск бота...")

    # Создание таблиц БД
    create_tables()
    logger.info("✅ База данных готова")

    # Инициализация бота
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # Инициализация диспетчера
    dp = Dispatcher()

    # Регистрация роутеров (ОДИН РАЗ!)
    dp.include_router(common.router)
    dp.include_router(client.router)
    dp.include_router(menu.router)

    # Удаление webhook при старте (если был)
    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("✅ Бот запущен и готов к работе!")
    logger.info(f"👤 Админы: {config.ADMIN_IDS}")

    # Запуск polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")