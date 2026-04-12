from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import text

from database.db import AsyncSessionLocal


def generate_referral_code(used_codes: set[str]) -> str:
    while True:
        code = uuid4().hex[:12]
        if code not in used_codes:
            used_codes.add(code)
            return code


async def get_existing_columns(session) -> set[str]:
    result = await session.execute(text("PRAGMA table_info(clients)"))
    rows = result.fetchall()
    return {row[1] for row in rows}


async def main():
    async with AsyncSessionLocal() as session:
        columns = await get_existing_columns(session)

        if "referral_code" not in columns:
            await session.execute(text("ALTER TABLE clients ADD COLUMN referral_code TEXT"))
        if "referrer_client_id" not in columns:
            await session.execute(text("ALTER TABLE clients ADD COLUMN referrer_client_id INTEGER"))
        if "referral_joined_at" not in columns:
            await session.execute(text("ALTER TABLE clients ADD COLUMN referral_joined_at DATETIME"))
        if "referral_reward_granted_at" not in columns:
            await session.execute(text("ALTER TABLE clients ADD COLUMN referral_reward_granted_at DATETIME"))
        if "referral_bonus_days_total" not in columns:
            await session.execute(
                text("ALTER TABLE clients ADD COLUMN referral_bonus_days_total INTEGER NOT NULL DEFAULT 0")
            )

        await session.commit()

        await session.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_clients_referral_code ON clients (referral_code)")
        )
        await session.execute(
            text("CREATE INDEX IF NOT EXISTS ix_clients_referrer_client_id ON clients (referrer_client_id)")
        )
        await session.commit()

        result = await session.execute(
            text("SELECT id, referral_code FROM clients")
        )
        rows = result.fetchall()

        used_codes = {
            row[1]
            for row in rows
            if row[1] is not None and str(row[1]).strip()
        }

        for client_id, referral_code in rows:
            if referral_code is not None and str(referral_code).strip():
                continue

            new_code = generate_referral_code(used_codes)
            await session.execute(
                text(
                    "UPDATE clients "
                    "SET referral_code = :referral_code "
                    "WHERE id = :client_id"
                ),
                {
                    "referral_code": new_code,
                    "client_id": client_id,
                },
            )

        await session.execute(
            text(
                "UPDATE clients "
                "SET referral_bonus_days_total = 0 "
                "WHERE referral_bonus_days_total IS NULL"
            )
        )
        await session.commit()

        result = await session.execute(
            text(
                "SELECT COUNT(*) FROM clients "
                "WHERE referral_code IS NULL OR TRIM(referral_code) = ''"
            )
        )
        missing_count = result.scalar_one()

    print("Referral migration completed.")
    print(f"Clients without referral_code after migration: {missing_count}")


if __name__ == "__main__":
    asyncio.run(main())
