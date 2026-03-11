import os
from dotenv import load_dotenv

load_dotenv()


def get_env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise ValueError(f"Не задана переменная окружения: {name}")
    return value


BOT_TOKEN = get_env("BOT_TOKEN", required=True)
DATABASE_URL = get_env("DATABASE_URL", required=True)

SUPPORT_USERNAME = get_env("SUPPORT_USERNAME", "@your_support")
SUPPORT_URL = get_env("SUPPORT_URL", "https://t.me/your_support")

XUI_BASE_URL = get_env("XUI_BASE_URL", required=True).rstrip("/")
XUI_WEB_BASE_PATH = get_env("XUI_WEB_BASE_PATH", "").strip("/")
XUI_USERNAME = get_env("XUI_USERNAME", required=True)
XUI_PASSWORD = get_env("XUI_PASSWORD", required=True)

VLESS_DOMAIN = get_env("VLESS_DOMAIN", required=True)
VLESS_PUBLIC_PORT = int(get_env("VLESS_PUBLIC_PORT", "443"))
VLESS_PATH = get_env("VLESS_PATH", "/vless")
VLESS_SECURITY = get_env("VLESS_SECURITY", "tls")
VLESS_SNI = get_env("VLESS_SNI", VLESS_DOMAIN)

PRICE_1_MONTH = get_env("PRICE_1_MONTH", "199 ₽")
PRICE_3_MONTHS = get_env("PRICE_3_MONTHS", "499 ₽")
PRICE_12_MONTHS = get_env("PRICE_12_MONTHS", "1490 ₽")

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", "")

YOOKASSA_AMOUNT_1_MONTH = os.getenv("YOOKASSA_AMOUNT_1_MONTH", "199.00")
YOOKASSA_AMOUNT_3_MONTHS = os.getenv("YOOKASSA_AMOUNT_3_MONTHS", "499.00")
YOOKASSA_AMOUNT_12_MONTHS = os.getenv("YOOKASSA_AMOUNT_12_MONTHS", "1490.00")

XRAY_INBOUND_PORT = int(get_env("XRAY_INBOUND_PORT", "10443"))

LOG_LEVEL = get_env("LOG_LEVEL", "INFO")

ADMIN_IDS = [
    int(x.strip())
    for x in get_env("ADMIN_IDS", "").split(",")
    if x.strip()
]