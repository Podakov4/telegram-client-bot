#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import select  # noqa: E402

from database.db import AsyncSessionLocal  # noqa: E402
from database.models import Client  # noqa: E402
from services.client_access import create_vpn_access_for_client_id  # noqa: E402


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client)
            .where(Client.is_active.is_(True))
            .order_by(Client.id.asc())
        )
        clients = list(result.scalars().all())

    print(f"Active clients found: {len(clients)}")

    ok_count = 0
    fail_count = 0

    for client in clients:
        print(
            "Sync "
            f"client_id={client.id} "
            f"telegram_id={client.telegram_id} "
            f"name={client.full_name}"
        )

        ok = await create_vpn_access_for_client_id(client.id)

        if ok:
            ok_count += 1
            print(f"  OK client_id={client.id}")
        else:
            fail_count += 1
            print(f"  FAIL client_id={client.id}")

    print("")
    print(f"Done. OK={ok_count}, FAIL={fail_count}")


if __name__ == "__main__":
    asyncio.run(main())
