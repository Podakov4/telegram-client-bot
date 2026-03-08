# config.py
import os
from dotenv import load_dotenv

# Загрузка переменных из .env
load_dotenv()

# Telegram
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Database
DATABASE_URL = os.getenv('DATABASE_URL')

# Admin
admin_ids_raw = os.getenv('ADMIN_IDS', '')
if admin_ids_raw:
    ADMIN_IDS = [int(x.strip()) for x in admin_ids_raw.split(',') if x.strip()]
else:
    ADMIN_IDS = []


# WireGuard
WG_SERVER_IP = os.getenv('WG_SERVER_IP')
WG_PORT = int(os.getenv('WG_PORT', 51820))
WG_SUBNET = os.getenv('WG_SUBNET')

VLESS_PORT = int(os.getenv('VLESS_PORT', 443))
VLESS_PATH = os.getenv('VLESS_PATH', '/vless')

# App
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
# 3x-ui Panel Configuration
XUI_PANEL_URL = os.getenv('XUI_PANEL_URL', 'http://127.0.0.1:2053')
XUI_USERNAME = os.getenv('XUI_USERNAME', 'xCwgwlzm8x')
XUI_PASSWORD = os.getenv('XUI_PASSWORD', 'JOc8S87g30')
XUI_WEB_BASE_PATH = os.getenv('XUI_WEB_BASE_PATH', 'YFBFh5UWZXQ7YxG6lt')

# Проверка что все переменные на месте
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env!")
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL не найден в .env!")
