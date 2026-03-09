#!/usr/bin/env python3
"""Проверка корректности настроек VLESS у всех клиентов"""

import sys
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db_session, Client
from services.stats import XrayStatsService
from config import VLESS_PORT, VLESS_PATH
import requests

print("=" * 70)
print("🔧 ПРОВЕРКА НАСТРОЕК VLESS")
print("=" * 70)

print(f"\n[1] КОНФИГУРАЦИЯ ПОДПИСКА:")
print(f"   Порт:    {VLESS_PORT}")
print(f"   Путь:    {VLESS_PATH}")
print(f"   Домен:   freeth.ru")

# Проверяем подключение к 3x-ui
stats_service = XrayStatsService()
if stats_service.test_connection():
    print("\n✅ Подключение к 3x-ui успешно!")
else:
    print("\n❌ Ошибка подключения к 3x-ui")
    sys.exit(1)

db = get_db_session()
try:
    clients = db.query(Client).all()
    print(f"\n[2] КЛИЕНТЫ В БАЗЕ ({len(clients)}):")

    # Получаем список пользователей из 3x-ui API
    inbound_users = set()
    try:
        emails = stats_service.get_all_clients()
        for email in emails:
            inbound_users.add(email)
            print(f"     ✓ API клиент: {email}")

    except Exception as e:
        print(f"\n⚠️ Не удалось получить список клиентов из API: {e}")

    for client in clients[:10]:
        status = "✅ Активен" if client.is_active else "❌ Деактивирован"
        api_status = "✔️ В инбоунде" if client.login in inbound_users else "❌ Нет в API"

        print(f"\n[{client.id}] {client.full_name or 'Без имени'}")
        print(f"   Telegram ID:     {client.telegram_id}")
        print(f"   Login:           {client.login}")
        print(f"   Статус:          {status}")
        print(f"   В инбоунде:      {api_status}")

        # Генерируем ссылку для теста
        path = VLESS_PATH.lstrip('/')
        print(f"   Ссылка (с path): https://freeth.ru{path}")

finally:
    db.close()

# Проверяем Nginx доступность пути
print("\n[3] ПРОВЕРКА NGINX (путь VLESS):")
try:
    response = requests.head("https://freeth.ru/vless", timeout=5, allow_redirects=False)
    print(f"   Статус код: {response.status_code}")
    print(f"   Сервер: {response.headers.get('Server', 'Unknown')}")
    if response.status_code != 404:
        print("   ✅ Пути доступны")
    else:
        print("   ⚠️ Путь /vless вернул 404")
except Exception as e:
    print(f"   ⚠️ Ошибка проверки: {e}")

# Проверяем SSL сертификат
print("\n[4] ПРОВЕРКА SSL СЕРТИФИКАТА:")
try:
    ssl_check = os.popen("""echo | openssl s_client -connect freeth.ru:443 -servername freeth.ru 2>/dev/null | openssl x509 -noout -dates""").read()
    print(f"   Даты действия:\n{ssl_check}")
except Exception as e:
    print(f"   ⚠️ Ошибка проверки SSL: {e}")

print("\n" + "=" * 70)
print("✅ ПРОВЕРКА ЗАВЕРШЕНА")
print("=" * 70)