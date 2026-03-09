#!/usr/bin/env python3
"""Финальный скрипт добавления клиентов в 3x-ui (без зависимостей от поля email)"""

import sys
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db_session, Client
from sqlalchemy import inspect
from config import XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD, XUI_WEB_BASE_PATH
import requests
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

session_token = None


def login():
    """Авторизация в 3x-ui (исправленный URL!)"""
    global session_token

    # ✅ ЭТОТ ПУТЬ РАБОТАЕТ ПО ТВОЕМУ ЛОГУ: /login
    base_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}" if XUI_WEB_BASE_PATH else XUI_PANEL_URL
    login_url = f"{base_url}/login"

    logger.info(f"🔑 Попытка входа в {login_url}")

    response = requests.post(
        login_url,
        json={"username": XUI_USERNAME, "password": XUI_PASSWORD},
        timeout=10
    )

    logger.info(f"   ✍️ Ответ сервера: код {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            session_token = response.cookies.get("3x-ui")
            logger.info("✅ Авторизация успешна!")
            return True
        else:
            logger.error(f"❌ Ошибка: {data.get('msg', 'Unknown')}")
    else:
        logger.error(f"❌ HTTP ошибка: {response.status_code}")

    return False


def get_client_email(client_obj):
    """Получить email клиента с fallback на login"""
    inspector = inspect(Client)
    column_names = [c.name for c in inspector.columns]

    # Если поле email есть в модели — используем его
    if "email" in column_names:
        if client_obj.email:
            return client_obj.email

    # Иначе используем login + домен
    if client_obj.login:
        return f"{client_obj.login}@freeth.ru"

    # Fallback на ID
    return f"user_{client_obj.id}@freeth.ru"


def add_client_to_inbound(inbound_id, email, tg_id):
    """Добавить клиента в inbound"""
    try:
        # Пробуем оба варианта URL addClient
        base_path = f"/{XUI_WEB_BASE_PATH}/panel/api/inbounds/addClient" if XUI_WEB_BASE_PATH else "/panel/api/inbounds/addClient"
        test_urls = [
            f"{XUI_PANEL_URL}{base_path}",
            f"{XUI_PANEL_URL}/panel/api/inbounds/addClient",
        ]

        client_data = {
            "email": email,
            "enabled": True,
            "expiryTime": 0,
            "totalGB": 0,
            "reset": 0,
            "tgId": str(tg_id),
            "flow": ""
        }

        payload = {"id": inbound_id, "settings": json.dumps({"clients": [client_data]})}
        headers = {"Cookie": f"3x-ui={session_token}"}

        success = False
        for url in test_urls:
            logger.info(f"   📩 URL: {url}")
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            logger.info(f"      Код: {response.status_code} | Текст: {response.text[:200]}")

            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    logger.info("      ✅ Клиент успешно добавлен!")
                    success = True
                    break

        return success

    except Exception as e:
        logger.error(f"❌ Ошибка создания клиента '{email}': {e}")
        return False


def get_existing_emails_from_api():
    """Получить список существующих email из API"""
    existing = set()

    base_path = f"/{XUI_WEB_BASE_PATH}/panel/api/inbounds/list" if XUI_WEB_BASE_PATH else "/panel/api/inbounds/list"
    list_url = f"{XUI_PANEL_URL}{base_path}"

    resp = requests.get(list_url, cookies={"3x-ui": session_token})

    if resp.status_code == 200:
        try:
            data = resp.json()
            if data.get("success"):
                count = 0
                for inbound in data.get("obj", []):
                    settings_raw = inbound.get("settings", "{}")
                    if isinstance(settings_raw, str):
                        try:
                            settings = json.loads(settings_raw)
                        except json.JSONDecodeError:
                            continue

                    for client in settings.get("clients", []):
                        email = client.get("email")
                        if email:
                            existing.add(email.lower())
                            count += 1

                logger.info(f"   Получено {count} клиентов из API")
            else:
                logger.warning(f"API ответ: {data.get('msg')}")
        except Exception as e:
            logger.error(f"Ошибка парсинга API: {e}")
    else:
        logger.error(f"Ошибка запроса к API: {resp.status_code}")

    return existing


def main():
    print("=" * 80)
    print("🔄 ДОБАВЛЕНИЕ КЛИЕНТОВ В 3x-ui (ФИНАЛЬНАЯ ВЕРСИЯ)")
    print("=" * 80)

    # 1. Авторизация ✅ (работает по твоему логу)
    if not login():
        logger.critical("Не удалось авторизоваться!")
        return 1

    db = get_db_session()
    try:
        # 2. Проверяем структуру модели
        logger.info("\n[1] Проверка модели Client:")
        inspector = inspect(Client)
        columns = [c.name for c in inspector.columns]
        logger.info(f"   Доступные поля: {columns}")
        has_email_field = "email" in columns
        logger.info(f"   Есть ли поле 'email': {'ДА' if has_email_field else 'НЕТ'}")

        # 3. Получаем ВСЕХ активных клиентов
        target_clients = db.query(Client).filter(Client.is_active == True).all()
        logger.info(f"\n[2] Найдено {len(target_clients)} активных клиентов:\n")

        for c in target_clients:
            email_field = get_client_email(c)
            logger.info(f"   - {c.full_name or 'Без имени'} ({c.telegram_id})")
            logger.info(f"      → email для 3x-ui: {email_field}\n")

        # 4. Получаем существующих из API
        existing_emails = get_existing_emails_from_api()
        logger.info(f"[3] Клиентов уже в API: {len(existing_emails)}")

        # 5. Добавляем новых
        added_count = 0
        skipped_count = 0
        inbound_id = 2  # VLESS via Nginx (подтверждено ранее)

        logger.info(f"\n💾 Начинаем добавление в inbound #{inbound_id}...\n")

        for c in target_clients:
            email = get_client_email(c)
            tg_id = c.telegram_id

            if email.lower() in existing_emails:
                logger.info(f"⏸️ Пропущен (уже в API): {email}")
                skipped_count += 1
                continue

            success = add_client_to_inbound(inbound_id, email, tg_id)

            if success:
                added_count += 1
                logger.info(f"✅ Добавлен: {email}\n")
            else:
                logger.error(f"❌ Ошибка: {email}\n")

        db.commit()

        print(f"\n{'=' * 80}")
        print(f"📊 РЕЗУЛЬТАТЫ:")
        print(f"   Успешно создано: {added_count}")
        print(f"   Пропущено (дубли): {skipped_count}")
        print(f"{'=' * 80}")

        return 0 if added_count > 0 else 1

    finally:
        db.close()


if __name__ == "__main__":
    exit(main())