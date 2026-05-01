#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from config import (
    XRAY_INBOUND_PORT,
    VLESS_PATH,
    VLESS_PUBLIC_PORT,
    VLESS_SECURITY,
)

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "database" / "clients.db"

US_PANEL_URL = os.getenv("US_XUI_BASE_URL", "https://panel-us.freeth.ru:54321")
US_PANEL_USERNAME = os.getenv("US_XUI_USERNAME", "admin")
US_PANEL_PASSWORD = os.getenv("US_XUI_PASSWORD", "change-me")
US_WEB_BASE_PATH = os.getenv("US_XUI_WEB_BASE_PATH", "")
US_INBOUND_PORT = int(os.getenv("US_XRAY_INBOUND_PORT", str(XRAY_INBOUND_PORT)))

US_VLESS_DOMAIN = os.getenv("US_VLESS_DOMAIN", "us.freeth.ru")
US_VLESS_PUBLIC_PORT = int(os.getenv("US_VLESS_PUBLIC_PORT", str(VLESS_PUBLIC_PORT)))
US_VLESS_PATH = os.getenv("US_VLESS_PATH", VLESS_PATH)
US_VLESS_SECURITY = os.getenv("US_VLESS_SECURITY", VLESS_SECURITY)
US_VLESS_SNI = os.getenv("US_VLESS_SNI", US_VLESS_DOMAIN)


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO vpn_nodes (
            code, name, display_name, country_code,
            panel_url, panel_username, panel_password, web_base_path,
            inbound_port, vless_domain, vless_public_port, vless_path,
            vless_security, vless_sni, is_active, sort_order,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(code) DO UPDATE SET
            name=excluded.name,
            display_name=excluded.display_name,
            country_code=excluded.country_code,
            panel_url=excluded.panel_url,
            panel_username=excluded.panel_username,
            panel_password=excluded.panel_password,
            web_base_path=excluded.web_base_path,
            inbound_port=excluded.inbound_port,
            vless_domain=excluded.vless_domain,
            vless_public_port=excluded.vless_public_port,
            vless_path=excluded.vless_path,
            vless_security=excluded.vless_security,
            vless_sni=excluded.vless_sni,
            is_active=excluded.is_active,
            sort_order=excluded.sort_order,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            "us",
            "United States",
            "🇺🇸 USA",
            "US",
            US_PANEL_URL,
            US_PANEL_USERNAME,
            US_PANEL_PASSWORD,
            US_WEB_BASE_PATH,
            US_INBOUND_PORT,
            US_VLESS_DOMAIN,
            US_VLESS_PUBLIC_PORT,
            US_VLESS_PATH,
            US_VLESS_SECURITY,
            US_VLESS_SNI,
            1,
            40,
        ),
    )

    conn.commit()
    conn.close()

    print(f"Done. US node added/updated in: {DB_PATH}")
    print(f"panel_url={US_PANEL_URL}")
    print(f"web_base_path={US_WEB_BASE_PATH}")
    print(f"inbound_port={US_INBOUND_PORT}")
    print(f"vless_domain={US_VLESS_DOMAIN}")
    print(f"vless_path={US_VLESS_PATH}")
    print(f"vless_sni={US_VLESS_SNI}")


if __name__ == "__main__":
    main()