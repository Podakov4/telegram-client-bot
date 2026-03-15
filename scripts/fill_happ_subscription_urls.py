import asyncio
import secrets

from sqlalchemy import select

from config import APP_BASE_URL
from database.db import AsyncSessionLocal
from database.models import Client


def make_token() -> str:
    return secrets.token_urlsafe(24)


async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Client))
        clients = result.scalars().all()

        updated = 0

        for client in clients:
            changed = False

            if not client.happ_subscription_token:
                client.happ_subscription_token = make_token()
                changed = True

            new_url = f"{APP_BASE_URL}/sub/{client.happ_subscription_token}"
            if client.happ_subscription_url != new_url:
                client.happ_subscription_url = new_url
                changed = True

            if changed:
                updated += 1

        await session.commit()
        print(f"Updated: {updated}")


if __name__ == "__main__":
    asyncio.run(main())