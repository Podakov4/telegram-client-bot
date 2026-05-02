#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from config import (  # noqa: E402
    XRAY_INBOUND_PORT,
    VLESS_PATH,
    VLESS_PUBLIC_PORT,
    VLESS_SECURITY,
)

DB_PATH = BASE_DIR / "database" / "clients.db"


def normalize_panel_url_and_path(panel_url: str, web_base_path: str) -> tuple[str, str]:
    raw_url = (panel_url or "").strip().rstrip("/")
    raw_path = (web_base_path or "").strip().strip("/")

    parsed = urlsplit(raw_url)
    url_path = parsed.path.strip("/")
    clean_url = urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")

    if not raw_path and url_path:
        raw_path = url_path

    return clean_url, raw_path


US_PANEL_URL_RAW = os.getenv("US_XUI_BASE_URL", "https://panel-us.freeth.ru:54321")
US_WEB_BASE_PATH_RAW = os.getenv("US_XUI_WEB_BASE_PATH", "")
US_PANEL_URL, US_WEB_BASE_PATH = normalize_panel_url_and_path(
    US_PANEL_URL_RAW,
    US_WEB_BASE_PATH_RAW,
)

US_PANEL_USERNAME = os.getenv("US_XUI_USERNAME", "admin")
US_PANEL_PASSWORD = os.getenv("US_XUI_PASSWORD", "change-me")
US_INBOUND_PORT = int(os.getenv("US_XRAY_INBOUND_PORT", str(XRAY_INBOUND_PORT)))

US_VLESS_DOMAIN = os.getenv("US_VLESS_DOMAIN", "us.freeth.ru")
US_VLESS_PUBLIC_PORT = int(os.getenv("US_VLESS_PUBLIC_PORT", str(VLESS_PUBLIC_PORT)))
US_VLESS_PATH = os.getenv("US_VLESS_PATH", VLESS_PATH)
US_VLESS_SECURITY = os.getenv("US_VLESS_SECURITY", VLESS_SECURITY)
US_VLESS_SNI = os.getenv("US_VLESS_SNI", US_VLESS_DOMAIN)


CREATE_VPN_NODES_SQL = """
CREATE TABLE IF NOT EXISTS vpn_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    country_code TEXT,
    panel_url TEXT NOT NULL,
    panel_username TEXT NOT NULL,
    panel_password TEXT NOT NULL,
    web_base_path TEXT,
    inbound_port INTEGER NOT NULL,
    vless_domain TEXT NOT NULL,
    vless_public_port INTEGER NOT NULL,
    vless_path TEXT NOT NULL,
    vless_security TEXT NOT NULL,
    vless_sni TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


UPSERT_NODE_SQL = """
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
"""


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.execute(CREATE_VPN_NODES_SQL)

    cur.execute(
        UPSERT_NODE_SQL,
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
