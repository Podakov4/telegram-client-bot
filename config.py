import os
from dotenv import load_dotenv

load_dotenv()


def get_env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise ValueError(f"Не задана переменная окружения: {name}")
    return value

ADMIN_IDS = [
    int(x) for x in get_env("ADMIN_IDS", "").split(",") if x.strip()
]
BOT_TOKEN = get_env("BOT_TOKEN", required=True)
DATABASE_URL = get_env("DATABASE_URL", required=True)

XUI_BASE_URL = get_env("XUI_BASE_URL", required=True).rstrip("/")
XUI_USERNAME = get_env("XUI_USERNAME", required=True)
XUI_PASSWORD = get_env("XUI_PASSWORD", required=True)

VLESS_DOMAIN = get_env("VLESS_DOMAIN", required=True)
VLESS_PUBLIC_PORT = int(get_env("VLESS_PUBLIC_PORT", "443"))
VLESS_PATH = get_env("VLESS_PATH", "/vless")
VLESS_SECURITY = get_env("VLESS_SECURITY", "tls")
VLESS_SNI = get_env("VLESS_SNI", VLESS_DOMAIN)

XRAY_INBOUND_PORT = int(get_env("XRAY_INBOUND_PORT", "10443"))

LOG_LEVEL = get_env("LOG_LEVEL", "INFO")