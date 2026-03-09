#!/usr/bin/env python3
"""Проверка корректности настроек VLESS у всех клиентов"""

import sys
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db_session, Client
from services.stats import XrayStatsService
from config import VLESS_PORT, VLESS_PATH
import requests

print("=" * 70)
print("🔧 ПРОВЕРКА НАСТРОЕК VLESS")
print("=" * 70)

# Получаем настройки
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

# Проверяем инбоуды
db = get_db_session()
try:
    clients = db.query(Client).all()
    print(f"\n[2] КЛИЕНТЫ В БАЗЕ ({len(clients)}):")
    
    # Получаем список активных пользователей
    inbound_emails = {}
    try:
        emails = stats_service.get_all_clients()
        for email in emails:
            inbound_emails[email] = True
            
    except Exception as e:
        print(f"⚠️ Не удалось получить список клиентов: {e}")
        
    for client in clients[:5]:  # Покажем первых 5
        status = "✅ Активен" if client.is_active else "❌ Деактивирован"
        
        # Проверка совпадения email и логинов
        email_match = "✅ OK" if client.email == client.login else "⚠️ РАЗЛИЧИЕ"
        
        print(f"\n[{client.id}] {client.full_name}")
        print(f"   Telegram ID:     {client.telegram_id}")
        print(f"   Email:           {client.email}")
        print(f"   Login:           {client.login} {email_match}")
        print(f"   Статус:          {status}")
        print(f"   Инбаунд в API:   {'✔️ Найден' if client.email in inbound_emails else '❌ Не найден'}")
        
        # Генерируем ссылку для теста
        link = f"vless://{client.email}@freeth.ru:{VLESS_PORT}?encryption=none&security=tls&sni=freeth.ru&type={VLESS_PATH.lstrip('/')}&host=freeth.ru"
        print(f"   Ссылка (с path):  https://freeth.ru{VLESS_PATH}")

finally:
    db.close()

# Проверяем Nginx
print("\n[3] ПРОВЕРКА NGINX (путь /vless):")
try:
    response = requests.head("https://freeth.ru/vless", timeout=5, allow_redirects=False)
    print(f"   Статус: {response.status_code}")
    print(f"   Response: {response.headers.get('Server', 'Nginx')}")
except Exception as e:
    print(f"   ⚠️ Ошибка: {e}")

print("\n" + "=" * 70)
print("✅ ПРОВЕРКА ЗАВЕРШЕНА")
print("=" * 70)

