# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Telegram bot + REST API for a VPN subscription service ("Freeth"). Clients subscribe via Telegram or a mobile app, pay via YooKassa, and get VLESS/Xray VPN access provisioned automatically across one or more geo nodes (managed via 3x-ui panels).

## Running the project

**Telegram bot:**
```bash
python bot.py
```

**FastAPI subscription/auth API:**
```bash
uvicorn app.subscription_api:app --reload
```

Both components share the same SQLite database (`database/clients.db`) and read config from `.env`.

## Environment setup

Copy `.env` and fill required values. Required variables:
- `BOT_TOKEN` — Telegram bot token
- `DATABASE_URL` — SQLite path, e.g. `sqlite+aiosqlite:///database/clients.db`
- `SECRET_KEY` — JWT signing secret
- `XUI_BASE_URL`, `XUI_USERNAME`, `XUI_PASSWORD` — primary 3x-ui panel
- `VLESS_DOMAIN` — primary VPN node domain
- `ADMIN_IDS` — comma-separated Telegram user IDs for admin access

Note: `DATABASE_URL` must use the `sqlite+aiosqlite://` prefix for async SQLAlchemy; the `.env` example uses `sqlite:///` which works only for sync drivers.

## Architecture

### Two entry points, one database

- `bot.py` — aiogram 3 polling bot; all Telegram interaction
- `app/subscription_api.py` — FastAPI app; REST endpoints consumed by mobile apps and VPN clients

### Layer structure

```
handlers/       aiogram routers (Telegram message/callback handlers)
services/       business logic (VPN provisioning, payments, auth, subscriptions)
database/
  db.py         SQLAlchemy async engine + session factories
  models.py     All ORM models
app/
  subscription_api.py   FastAPI app with all REST routes
keyboards/      aiogram reply/inline keyboard builders
utils/          shared helpers (happ_shared.py — instruction texts)
scripts/        one-off migration/maintenance scripts (run manually)
```

### Key services

| File | Responsibility |
|------|---------------|
| `services/client_access.py` | VPN provisioning: create/disable/sync Xray access across all active `VpnNode` rows; syncs legacy `Client` fields from primary node |
| `services/vless.py` | HTTP client wrapping the 3x-ui panel API (`VLESSManager`); builds VLESS URLs |
| `services/auth_service.py` | JWT access/refresh tokens, login codes, email OTP, device sessions |
| `services/payments.py` | YooKassa payment creation + webhook processing; subscription activation |
| `services/subscriptions.py` | Subscription status queries; expiry notifications |
| `services/device_service.py` | Device tracking and per-plan device limits |
| `services/email_sender.py` | Email dispatch (SMTP or Resend provider) |

### Multi-node VPN model

`VpnNode` rows in the DB define active server nodes. Each client gets a `ClientVpnAccess` row per node. The legacy `Client.xui_uuid` / `subscription_link` fields are kept in sync from the primary node for backward compatibility. `services/client_access.py` always fans out to all active nodes.

### Database

SQLAlchemy async (aiosqlite). Schema is created via `create_tables()` called at bot startup — there is no migration framework. Schema changes require manual `scripts/add_*.py` migration scripts.

Session patterns:
- `session_scope()` — async context manager with auto commit/rollback, used in scripts
- `AsyncSessionLocal()` direct use — used in most service functions
- `get_db()` — FastAPI dependency injection

## Scripts

The `scripts/` directory contains standalone migration/maintenance scripts. Run them directly:
```bash
python scripts/send_expiring_notifications.py
python scripts/sync_active_clients_vpn_access.py
```

## Tests

The `tests/` directory exists but is currently empty.
