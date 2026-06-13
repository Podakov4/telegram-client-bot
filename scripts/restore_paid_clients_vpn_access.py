"""
Restore VPN access for all clients whose subscription is paid/active
but whose ClientVpnAccess rows are all disabled (is_enabled=False).

Run once to fix the state left by the httpx follow_redirects bug.
"""

import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Client, ClientVpnAccess
from services.client_access import create_vpn_access_for_client_id, is_client_subscription_active

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def find_affected_clients() -> list[int]:
    """Return IDs of clients that are subscription-active but have all accesses disabled."""
    now = datetime.utcnow()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(
                Client.is_active == True,
                Client.is_paid == True,
                Client.paid_until > now,
                Client.status == "active",
            )
        )
        paid_clients = result.scalars().all()

        affected = []
        for client in paid_clients:
            accesses = (await session.execute(
                select(ClientVpnAccess).where(ClientVpnAccess.client_id == client.id)
            )).scalars().all()

            if not accesses:
                continue

            all_disabled = all(not a.is_enabled for a in accesses)
            if all_disabled:
                logger.info(
                    "Client id=%s (%s) is paid but all %d accesses are disabled",
                    client.id,
                    client.full_name or client.telegram_id,
                    len(accesses),
                )
                affected.append(client.id)

    return affected


async def main():
    logger.info("Scanning for paid clients with fully-disabled VPN accesses...")
    affected = await find_affected_clients()

    if not affected:
        logger.info("No affected clients found.")
        return

    logger.info("Found %d affected clients: %s", len(affected), affected)

    ok_count = 0
    fail_count = 0

    for client_id in affected:
        logger.info("Restoring VPN access for client_id=%s ...", client_id)
        try:
            ok = await create_vpn_access_for_client_id(client_id)
            if ok:
                logger.info("  OK client_id=%s", client_id)
                ok_count += 1
            else:
                logger.warning("  PARTIAL/FAIL client_id=%s", client_id)
                fail_count += 1
        except Exception:
            logger.exception("  EXCEPTION client_id=%s", client_id)
            fail_count += 1

    logger.info("Done. Success: %d, Failed/partial: %d", ok_count, fail_count)


asyncio.run(main())
