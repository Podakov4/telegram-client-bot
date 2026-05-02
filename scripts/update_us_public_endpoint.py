#!/usr/bin/env python3
import argparse
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse, quote


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
DB_PATH = PROJECT_ROOT / "database" / "clients.db"


DEFAULTS = {
    "US_VLESS_DOMAIN": "us-via-de.freeth.ru",
    "US_VLESS_PUBLIC_PORT": "443",
    "US_VLESS_PATH": "/vless",
    "US_VLESS_SECURITY": "tls",
    "US_VLESS_SNI": "us-via-de.freeth.ru",
}


def load_env_file(path: Path) -> dict:
    result = {}

    if not path.exists():
        return result

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        result[key] = value

    return result


def get_setting(env: dict, key: str) -> str:
    return os.getenv(key) or env.get(key) or DEFAULTS[key]


def table_columns(cur: sqlite3.Cursor, table: str) -> set[str]:
    return {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}


def rebuild_vless_link(link: str, domain: str, port: int, path: str, security: str, sni: str) -> str:
    parsed = urlparse(link)

    if parsed.scheme != "vless":
        return link

    username = parsed.username or ""
    fragment = parsed.fragment or ""

    query_pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))

    query_pairs["type"] = "ws"
    query_pairs["security"] = security
    query_pairs["encryption"] = query_pairs.get("encryption") or "none"
    query_pairs["path"] = path
    query_pairs["host"] = domain
    query_pairs["sni"] = sni

    query = urlencode(query_pairs, doseq=True)

    netloc = f"{username}@{domain}:{port}"

    return urlunparse((
        "vless",
        netloc,
        "",
        "",
        query,
        fragment,
    ))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update USA public VLESS endpoint to us-via-de.freeth.ru without touching other nodes."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes to database. Without this flag script runs in dry-run mode.",
    )
    args = parser.parse_args()

    env = load_env_file(ENV_PATH)

    domain = get_setting(env, "US_VLESS_DOMAIN")
    public_port = int(get_setting(env, "US_VLESS_PUBLIC_PORT"))
    vless_path = get_setting(env, "US_VLESS_PATH")
    security = get_setting(env, "US_VLESS_SECURITY")
    sni = get_setting(env, "US_VLESS_SNI")

    print("PROJECT_ROOT:", PROJECT_ROOT)
    print("DB_PATH:", DB_PATH)
    print("MODE:", "APPLY" if args.apply else "DRY-RUN")
    print()
    print("New USA public endpoint:")
    print("domain:", domain)
    print("port:", public_port)
    print("path:", vless_path)
    print("security:", security)
    print("sni:", sni)
    print()

    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    vpn_cols = table_columns(cur, "vpn_nodes")
    access_cols = table_columns(cur, "client_vpn_access")

    us_node = cur.execute("""
        SELECT id, code, display_name, vless_domain, vless_public_port, vless_path, vless_security, vless_sni
        FROM vpn_nodes
        WHERE code = 'us'
    """).fetchone()

    if not us_node:
        raise SystemExit("ERROR: vpn_nodes row with code='us' not found")

    node_id = us_node[0]

    print("Current USA node:")
    print(us_node)
    print()

    update_node_sql = """
        UPDATE vpn_nodes
        SET
            vless_domain = ?,
            vless_public_port = ?,
            vless_path = ?,
            vless_security = ?,
            vless_sni = ?,
            display_name = ?,
            is_active = 1
        WHERE code = 'us'
    """

    node_params = (
        domain,
        public_port,
        vless_path,
        security,
        sni,
        "🇺🇸 USA",
    )

    rows = cur.execute("""
        SELECT cva.id, cva.client_id, cva.subscription_link
        FROM client_vpn_access cva
        JOIN vpn_nodes vn ON vn.id = cva.node_id
        WHERE vn.code = 'us'
        ORDER BY cva.client_id
    """).fetchall()

    print("USA access rows:", len(rows))
    print()

    changed_links = []

    for access_id, client_id, old_link in rows:
        if not old_link:
            continue

        new_link = rebuild_vless_link(
            old_link,
            domain=domain,
            port=public_port,
            path=vless_path,
            security=security,
            sni=sni,
        )

        if new_link != old_link:
            changed_links.append((access_id, client_id, old_link, new_link))

    print("Links to update:", len(changed_links))
    print()

    for access_id, client_id, old_link, new_link in changed_links[:5]:
        old_safe = old_link.split("@", 1)[1] if "@" in old_link else old_link
        new_safe = new_link.split("@", 1)[1] if "@" in new_link else new_link

        print("client_id:", client_id)
        print("old:", old_safe)
        print("new:", new_safe)
        print("---")

    if len(changed_links) > 5:
        print(f"... and {len(changed_links) - 5} more")
        print()

    if not args.apply:
        print("DRY-RUN only. To write changes, run:")
        print("python3 scripts/update_us_public_endpoint.py --apply")
        conn.close()
        return

    cur.execute(update_node_sql, node_params)

    for access_id, client_id, old_link, new_link in changed_links:
        cur.execute("""
            UPDATE client_vpn_access
            SET subscription_link = ?
            WHERE id = ?
        """, (new_link, access_id))

    conn.commit()

    updated_node = cur.execute("""
        SELECT code, display_name, panel_url, inbound_port, vless_domain, vless_public_port, vless_path, vless_security, vless_sni, is_active
        FROM vpn_nodes
        WHERE code = 'us'
    """).fetchone()

    print()
    print("UPDATED USA node:")
    print(updated_node)

    conn.close()

    print()
    print("Done.")


if __name__ == "__main__":
    main()