import asyncio
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from aiogram import Bot  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.utils.keyboard import InlineKeyboardBuilder  # noqa: E402

import config  # noqa: E402
from services.subscriptions import (  # noqa: E402
    get_expiring_clients_for_notice,
    get_expired_clients_for_notice,
    mark_expiring_notice_sent,
    mark_expired_notice_sent,
    disable_expired_subscriptions,
)

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

    disabled_count = await disable_expired_subscriptions()
    logger.info("Автоотключено просроченных подписок: %s", disabled_count)

    expiring_clients = await get_expiring_clients_for_notice(days=3)
    expired_clients = await get_expired_clients_for_notice()

    sent_expiring = 0
    sent_expired = 0

    for client in expiring_clients:
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
            await mark_expiring_notice_sent(client.id)
            sent_expiring += 1
            logger.info("Предупреждение отправлено telegram_id=%s", client.telegram_id)

        except Exception as e:
            logger.exception(
                "Не удалось отправить предупреждение telegram_id=%s: %s",
                client.telegram_id,
                e,
            )

    for client in expired_clients:
        try:
            text = (
                f"Здравствуйте, {client.full_name or 'пользователь'}!\n\n"
                "Срок действия вашей подписки истек.\n\n"
                "Чтобы восстановить доступ, продлите подписку."
            )

            await bot.send_message(
                chat_id=int(client.telegram_id),
                text=text,
                reply_markup=renewal_keyboard(),
            )
            await mark_expired_notice_sent(client.id)
            sent_expired += 1
            logger.info("Сообщение об истечении отправлено telegram_id=%s", client.telegram_id)

        except Exception as e:
            logger.exception(
                "Не удалось отправить сообщение об истечении telegram_id=%s: %s",
                client.telegram_id,
                e,
            )

    logger.info(
        "Готово. Предупреждений: %s, сообщений об истечении: %s",
        sent_expiring,
        sent_expired,
    )
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())