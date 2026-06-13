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
utils/          shared helpers
  happ_shared.py  instruction texts sent to clients
  notes.py        canonical key=value notes parser (parse_notes, dump_notes, get_note_int, upsert_note)
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

### Shared handler helpers

`handlers/common.py` owns helpers used across multiple handler modules:
- `client_has_trial_used(client)` — checks `trial_used=true` in `client.notes`
- `client_has_active_access(client)` — checks `is_active + subscription_link` or unexpired `paid_until`
- `keyboard_for_client(client, user_id)` — builds the main reply keyboard
- `REFERRAL_BONUS_DAYS` — authoritative constant for referral bonus days

Import these from `handlers/common` rather than redefining them.

### Multi-node VPN model

`VpnNode` rows in the DB define active server nodes. Each client gets a `ClientVpnAccess` row per node. The legacy `Client.xui_uuid` / `subscription_link` fields are kept in sync from the primary node for backward compatibility. `services/client_access.py` always fans out to all active nodes.

### VPN subscription link fallback

`_collect_subscription_links` in `client_access.py` follows this priority:
1. Enabled `ClientVpnAccess.subscription_link` rows (one per active node) — normal case
2. Legacy `Client.subscription_link` — **only** when the client has zero `ClientVpnAccess` rows (pre-multi-node clients)

If all `ClientVpnAccess` rows exist but are disabled (expired subscription), the fallback is intentionally skipped — returning the stale legacy link would let a disabled client through.

### `client.notes` convention

`Client.notes` stores metadata as plain `key=value` lines, one per line. Non-`key=value` lines are preserved as raw annotations.

Known keys:

| Key | Values | Set by |
|-----|--------|--------|
| `plan_code` | `1m`, `3m`, `12m`, `trial_7d`, `admin_Nd`, etc. | `payments.py` on activation |
| `max_devices` | integer ≥ 1 | `payments.py` on activation; admin panel |
| `trial_used` | `true` | `payments.py` on trial activation |

Use `utils/notes.py` functions (`parse_notes`, `dump_notes`, `get_note_int`, `upsert_note`) to read/write notes. Do **not** parse `client.notes` manually in new code.

`limitIp` in 3x-ui is set equal to `max_devices` during every VPN provisioning call, enforcing the device limit at the protocol level.

### Device limit enforcement

Limits are enforced at two layers:
1. **App auth layer** (`services/device_service.py`) — `ensure_device_slot_available` blocks login when active device count ≥ `max_devices`
2. **VPN node layer** — `limitIp` field in 3x-ui is kept in sync with `max_devices` on every `create_vpn_access_for_client_id` call

`GET /sub/{token}` (subscription URL endpoint) is open and not device-limited — only the app login flow is restricted.

### Referral program

- `Client.referral_code` — unique code per client; set at registration
- `Client.referrer_client_id` — FK to the referring client
- `Client.referral_reward_granted_at` — set when referrer is rewarded (prevents double reward)
- `REFERRAL_BONUS_DAYS = 20` — bonus days granted to the referrer after the referred client's first paid subscription
- Reward is granted atomically inside `process_successful_payment` via `grant_referral_bonus_if_eligible`

### Database

SQLAlchemy async (aiosqlite). Schema is created via `create_tables()` called at bot startup — there is no migration framework. Schema changes require manual `scripts/add_*.py` migration scripts.

Session patterns:
- `session_scope()` — async context manager with auto commit/rollback, used in scripts
- `AsyncSessionLocal()` direct use — used in most service functions
- `get_db()` — FastAPI dependency injection

## Systemd services

Both processes run as systemd units on the server:

| Service | Command |
|---------|---------|
| `telegram-client-bot.service` | Telegram polling bot (`bot.py`) |
| `freeth-subscription.service` | FastAPI uvicorn (`app.subscription_api`) |

```bash
# Restart
systemctl restart telegram-client-bot.service
systemctl restart freeth-subscription.service

# Logs (live)
journalctl -u telegram-client-bot.service -f
journalctl -u freeth-subscription.service -f
```

## Scripts

The `scripts/` directory contains standalone migration/maintenance scripts. Run them directly:
```bash
python scripts/send_expiring_notifications.py
python scripts/sync_active_clients_vpn_access.py
```

## Tests

Run with:
```bash
venv/bin/pytest tests/ -v
```

132 tests covering pure/sync/async helpers across all layers:

| File | What's tested |
|------|--------------|
| `test_utils_notes.py` | `parse_notes`, `dump_notes`, `get_note_int`, `upsert_note` |
| `test_services_payments.py` | Month/day conversion, plan pricing, device limits by plan |
| `test_services_client_access.py` | `make_xui_email`, `is_client_subscription_active`, URL builders |
| `test_services_subscriptions.py` | `is_subscription_active`, `serialize_subscription_status` |
| `test_handlers_admin.py` | Notes parsing, `split_admin_text`, `format_client_card` |
| `test_handlers_client.py` | Access flags, referral link, access/device formatting |

`tests/conftest.py` provides `make_client()` and `make_history_row()` factory helpers that return `SimpleNamespace` objects — use these when testing any function that takes a `Client` argument, to avoid DB dependencies.
