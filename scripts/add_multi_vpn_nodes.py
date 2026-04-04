#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from config import (
    XRAY_INBOUND_PORT,
    XUI_BASE_URL,
    XUI_PASSWORD,
    XUI_USERNAME,
    XUI_WEB_BASE_PATH,
    VLESS_DOMAIN,
    VLESS_PATH,
    VLESS_PUBLIC_PORT,
    VLESS_SECURITY,
    VLESS_SNI,
)

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "database" / "clients.db"

DE_PANEL_URL = os.getenv("DE_XUI_BASE_URL", "https://panel-de.freeth.ru")
DE_PANEL_USERNAME = os.getenv("DE_XUI_USERNAME", "admin")
DE_PANEL_PASSWORD = os.getenv("DE_XUI_PASSWORD", "change-me")
DE_WEB_BASE_PATH = os.getenv("DE_XUI_WEB_BASE_PATH", "")
DE_INBOUND_PORT = int(os.getenv("DE_XRAY_INBOUND_PORT", str(XRAY_INBOUND_PORT)))
DE_VLESS_DOMAIN = os.getenv("DE_VLESS_DOMAIN", "de.freeth.ru")
DE_VLESS_PUBLIC_PORT = int(os.getenv("DE_VLESS_PUBLIC_PORT", str(VLESS_PUBLIC_PORT)))
DE_VLESS_PATH = os.getenv("DE_VLESS_PATH", VLESS_PATH)
DE_VLESS_SECURITY = os.getenv("DE_VLESS_SECURITY", VLESS_SECURITY)
DE_VLESS_SNI = os.getenv("DE_VLESS_SNI", DE_VLESS_DOMAIN)


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.execute(
        """
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
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS client_vpn_access (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            node_id INTEGER NOT NULL,
            xui_uuid TEXT,
            xui_email TEXT,
            subscription_link TEXT,
            is_enabled INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
            FOREIGN KEY (node_id) REFERENCES vpn_nodes(id) ON DELETE CASCADE,
            UNIQUE (client_id, node_id)
        )
        """
    )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_client_vpn_access_client_id
        ON client_vpn_access(client_id)
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_client_vpn_access_node_id
        ON client_vpn_access(node_id)
        """
    )

    nodes = [
        {
            "code": "nl",
            "name": "Netherlands",
            "display_name": "🇳🇱 Amsterdam",
            "country_code": "NL",
            "panel_url": XUI_BASE_URL,
            "panel_username": XUI_USERNAME,
            "panel_password": XUI_PASSWORD,
            "web_base_path": XUI_WEB_BASE_PATH,
            "inbound_port": XRAY_INBOUND_PORT,
            "vless_domain": VLESS_DOMAIN,
            "vless_public_port": VLESS_PUBLIC_PORT,
            "vless_path": VLESS_PATH,
            "vless_security": VLESS_SECURITY,
            "vless_sni": VLESS_SNI,
            "is_active": 1,
            "sort_order": 10,
        },
        {
            "code": "de",
            "name": "Germany",
            "display_name": "🇩🇪 Germany",
            "country_code": "DE",
            "panel_url": DE_PANEL_URL,
            "panel_username": DE_PANEL_USERNAME,
            "panel_password": DE_PANEL_PASSWORD,
            "web_base_path": DE_WEB_BASE_PATH,
            "inbound_port": DE_INBOUND_PORT,
            "vless_domain": DE_VLESS_DOMAIN,
            "vless_public_port": DE_VLESS_PUBLIC_PORT,
            "vless_path": DE_VLESS_PATH,
            "vless_security": DE_VLESS_SECURITY,
            "vless_sni": DE_VLESS_SNI,
            "is_active": 1,
            "sort_order": 20,
        },
    ]

    for node in nodes:
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
                node["code"],
                node["name"],
                node["display_name"],
                node["country_code"],
                node["panel_url"],
                node["panel_username"],
                node["panel_password"],
                node["web_base_path"],
                node["inbound_port"],
                node["vless_domain"],
                node["vless_public_port"],
                node["vless_path"],
                node["vless_security"],
                node["vless_sni"],
                node["is_active"],
                node["sort_order"],
            ),
        )

    nl_node_id = cur.execute(
        "SELECT id FROM vpn_nodes WHERE code = 'nl'"
    ).fetchone()[0]

    cur.execute(
        """
        INSERT OR IGNORE INTO client_vpn_access (
            client_id,
            node_id,
            xui_uuid,
            xui_email,
            subscription_link,
            is_enabled,
            created_at,
            updated_at
        )
        SELECT
            c.id,
            ?,
            c.xui_uuid,
            c.xui_email,
            c.subscription_link,
            CASE WHEN c.is_active = 1 AND c.is_paid = 1 THEN 1 ELSE 0 END,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM clients c
        WHERE (c.xui_uuid IS NOT NULL OR c.subscription_link IS NOT NULL)
        """,
        (nl_node_id,),
    )

    conn.commit()
    conn.close()

    print(f"Done. Multi-node tables are ready in: {DB_PATH}")
    print("NL node synced from current config and legacy client access copied to client_vpn_access.")
    print("DE node values came from environment variables DE_XUI_* / DE_VLESS_*.")


if __name__ == "__main__":
    main()
