#!/usr/bin/env python3
"""Diagnose per-node VPN access for a single client.

Usage:
    python scripts/diagnose_client_access.py <telegram_id_or_client_id>

For each active VPN node it reports:
  - the DB client_vpn_access row (is_enabled, stored uuid/email/link)
  - whether the node panel is reachable / login works
  - whether the client actually exists on that panel and is enabled
This pinpoints why a client ends up with fewer working nodes than expected.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import select  # noqa: E402

from database.db import AsyncSessionLocal  # noqa: E402
from database.models import Client, ClientVpnAccess, VpnNode  # noqa: E402
from services.client_access import build_node_config  # noqa: E402
from services.vless import VLESSManager  # noqa: E402


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/diagnose_client_access.py <telegram_id_or_client_id>")
        sys.exit(1)

    key = sys.argv[1].strip()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(
                (Client.telegram_id == key) | (Client.id == (int(key) if key.isdigit() else -1))
            )
        )
        client = result.scalars().first()
        if client is None:
            print(f"Client not found for key={key}")
            sys.exit(1)

        print("=" * 60)
        print(f"client id={client.id} tg={client.telegram_id} name={client.full_name!r}")
        print(f"  is_active={client.is_active} is_paid={client.is_paid} "
              f"status={client.status} paid_until={client.paid_until}")
        print("=" * 60)

        nodes = (await session.execute(
            select(VpnNode).where(VpnNode.is_active.is_(True))
            .order_by(VpnNode.sort_order.asc(), VpnNode.id.asc())
        )).scalars().all()

        access_rows = (await session.execute(
            select(ClientVpnAccess).where(ClientVpnAccess.client_id == client.id)
        )).scalars().all()
        access_by_node = {a.node_id: a for a in access_rows}

    for node in nodes:
        print(f"\n--- node {node.code} ({node.display_name}) panel={node.panel_url} ---")
        a = access_by_node.get(node.id)
        if a is None:
            print("  DB: NO client_vpn_access row")
        else:
            print(f"  DB: is_enabled={a.is_enabled} xui_email={a.xui_email!r}")
            print(f"      uuid={a.xui_uuid}")
            print(f"      link={a.subscription_link}")

        try:
            async with VLESSManager(node_config=build_node_config(node)) as manager:
                logged_in = await manager.login()
                print(f"  PANEL: login={'OK' if logged_in else 'FAILED'}")
                if not logged_in:
                    continue

                inbound_id = await manager.find_inbound_by_port(manager.inbound_port)
                print(f"  PANEL: inbound for port {manager.inbound_port}: {inbound_id}")
                if not inbound_id:
                    continue

                found = None
                if a and (a.xui_email or a.xui_uuid):
                    found = await manager.find_client(email=a.xui_email, client_uuid=a.xui_uuid)
                if found:
                    _, obj, _ = found
                    print(f"  PANEL: client FOUND enable={obj.get('enable')} "
                          f"expiryTime={obj.get('expiryTime')} email={obj.get('email')!r}")
                else:
                    print("  PANEL: client NOT FOUND on this panel")
        except Exception as exc:
            print(f"  PANEL: ERROR {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
