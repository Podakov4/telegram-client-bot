#!/usr/bin/env python3
"""Конфигурация приложения VLESS Telegram Bot"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Database
DATABASE_URL = os.getenv('DATABASE_URL')

# Admin IDs
admin_ids_raw = os.getenv('ADMIN_IDS', '')
if admin_ids_raw:
    ADMIN_IDS = [int(x.strip()) for x in admin_ids_raw.split(',') if x.strip()]
else:
    ADMIN_IDS = []

# VLESS Settings
VLESS_PORT = int(os.getenv('VLESS_PORT', '10443'))
VLESS_PATH = os.getenv('VLESS_PATH', '/vless')
VLESS_DOMAIN = os.getenv('VLESS_DOMAIN', 'freeth.ru')

# 3x-ui Panel Configuration
XUI_PANEL_URL = os.getenv('XUI_PANEL_URL', 'http://72.56.118.169:2053')
XUI_USERNAME = os.getenv('XUI_USERNAME', 'xCwgwlzm8x')
XUI_PASSWORD = os.getenv('XUI_PASSWORD', 'JOc8S87g30')
XUI_WEB_BASE_PATH = os.getenv('XUI_WEB_BASE_PATH', 'YFBFh5UWZXQ7YxG6lt')

# App Settings
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# Проверка обязательных параметров
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env!")
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL не найден в .env!")

print(f"✅ Конфигурация загружена успешно")