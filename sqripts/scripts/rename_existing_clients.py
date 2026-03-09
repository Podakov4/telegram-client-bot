import asyncio
import logging
import re

from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def make_xui_email(telegram_id: str, full_name: str | None, fallback_id: int) -> str:
    base_name = (full_name or f"user_{fallback_id}").lower().strip()
    base_name = base_name.replace(" ", "_")
    base_name = re.sub(r"[^a-zA-Z0-9_а-яА-ЯёЁ]", "", base_name)
    base_name = base_name[:24] if base_name else f"user_{fallback_id}"
    return f"tg_{telegram_id}_{base_name}"


async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Client))
        clients = result.scalars().all()

        if not clients:
            logger.info("Клиенты не найдены.")
            return

        for client in clients:
            new_label = make_xui_email(
                telegram_id=client.telegram_id,
                full_name=client.full_name,
                fallback_id=client.id,
            )

            old_login = client.login
            old_xui_email = client.xui_email

            if not client.login:
                client.login = new_label

            if not client.xui_email:
                client.xui_email = new_label

            logger.info(
                "client id=%s telegram_id=%s old_login=%s old_xui_email=%s -> new_label=%s",
                client.id,
                client.telegram_id,
                old_login,
                old_xui_email,
                new_label,
            )

        await session.commit()
        logger.info("Обновление завершено.")


if __name__ == "__main__":
    asyncio.run(main())