import asyncio
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Client
from services.vless import VLESSManager


async def main():
    manager = VLESSManager()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.xui_uuid.is_not(None))
        )
        clients = result.scalars().all()

        updated = 0

        for client in clients:
            client.subscription_link = manager.build_vless_link(client.xui_uuid)
            updated += 1

        await session.commit()
        print(f"Updated subscription links: {updated}")


if __name__ == "__main__":
    asyncio.run(main())