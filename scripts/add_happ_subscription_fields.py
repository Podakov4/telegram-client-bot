import asyncio
from sqlalchemy import text

from database.db import AsyncSessionLocal


async def column_exists(session, table_name: str, column_name: str) -> bool:
    result = await session.execute(text(f"PRAGMA table_info({table_name})"))
    rows = result.fetchall()
    return any(row[1] == column_name for row in rows)


async def main():
    async with AsyncSessionLocal() as session:
        if not await column_exists(session, "clients", "happ_subscription_token"):
            await session.execute(
                text("ALTER TABLE clients ADD COLUMN happ_subscription_token VARCHAR")
            )

        if not await column_exists(session, "clients", "happ_subscription_url"):
            await session.execute(
                text("ALTER TABLE clients ADD COLUMN happ_subscription_url TEXT")
            )

        await session.commit()
        print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(main())