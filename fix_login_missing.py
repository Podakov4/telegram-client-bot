#!/usr/bin/env python3
"""Скрипт добавления клиентов в 3x-ui (исправлено под схему с NULL email)"""

import sys
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db_session, Client
import requests
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Настройки подключения к панели (можно заменить на импорт из config.py)
XUI_PANEL_URL = "http://72.56.118.169:2053"
XUI_WEB_BASE_PATH = "YFBFh5UWZXQ7YxG6lt"
XUI_USERNAME = "xCwgwlzm8x"
XUI_PASSWORD = "JOc8S87g30"

session_token = None


def login():
    """Авторизация в 3x-ui"""
    global session_token

    login_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/admin/login"

    response = requests.post(
        login_url,
        json={"username": XUI_USERNAME, "password": XUI_PASSWORD},
        timeout=10
    )

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            session_token = response.cookies.get("3x-ui")
            logger.info("✅ Авторизация в 3x-ui успешна!")
            return True

    logger.error(f"❌ Ошибка входа: {response.status_code}")
    return False


def add_client_to_inbound(inbound_id, email, tg_id):
    """Добавление клиента в конкретный инбоуд"""
    try:
        url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/addClient"

        client_data = {
            "email": email,
            "enabled": True,
            "expiryTime": 0,  # Без срока действия
            "totalGB": 0,  # Безлимитный трафик
            "reset": 0,  # Бессрочный
            "tgId": str(tg_id),  # Telegram ID для привязки
            "flow": ""  # Стандартный поток
        }

        payload = {
            "id": inbound_id,
            "settings": json.dumps({
                "clients": [client_data]
            })
        }

        headers = {"Cookie": f"3x-ui={session_token}"}
        response = requests.post(url, json=payload, headers=headers, timeout=30)

        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                return True

        logger.warning(f"⚠️ Не удалось создать {email}: {response.text[:100]}")
        return False

    except Exception as e:
        logger.error(f"❌ Ошибка создания {email}: {e}")
        return False


def main():
    print("=" * 80)
    print("🔄 ДОБАВЛЕНИЕ КЛИЕНТОВ В 3x-ui (КОНЕЧНАЯ ВЕРСИЯ)")
    print("=" * 80)

    # 1. Вход в систему
    if not login():
        logger.critical("Невозможно продолжить без авторизации!")
        return 1

    db = get_db_session()
    try:
        # 2. Получаем активных клиентов с пустым email, но имеющим login
        # Важная часть фильтрации по схеме БД: email IS NULL AND login IS NOT NULL
        target_clients = db.query(Client).filter(
            Client.is_active == True,
            Client.email == None,  # Проверка именно на NULL
            ~Client.login.in_(['', None])
        ).all()

        logger.info(f"[1] Найдено клиентов для добавления: {len(target_clients)}")

        # Получаем список существующих email из панели, чтобы избежать дублей
        existing_emails = set()
        list_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/list"
        resp = requests.get(list_url, cookies={"3x-ui": session_token})

        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
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
                            existing_emails.add(email.lower())

        logger.info(f"[2] Клиентов уже в панели: {len(existing_emails)}")

        # Идём по списку и добавляем
        added_count = 0
        skipped_count = 0
        error_count = 0

        # Инбоуд #2 соответствует VLESS через Nginx (проверено ранее)
        inbound_id = 2

        for c in target_clients:
            # КРИТИЧЕСКИЙ МОМЕНТ: строим email из login
            if c.login:
                email = f"{c.login}@freeth.ru"
            else:
                email = f"user_{c.id}@freeth.ru"

            tg_id = c.telegram_id

            # Пропускаем, если уже есть
            if email.lower() in existing_emails:
                logger.info(f"⏸️ Пропущен (уже в API): {email}")
                skipped_count += 1
                continue

            success = add_client_to_inbound(inbound_id, email, tg_id)

            if success:
                # Обновляем email в базе, чтобы в следующий раз не пытаться добавлять
                c.email = email
                added_count += 1
                logger.info(f"✅ Добавлен: {email}")
            else:
                error_count += 1

        db.commit()

        print(f"\n{'=' * 80}")
        print(f"📊 РЕЗУЛЬТАТЫ:")
        print(f"   Успешно создано: {added_count}")
        print(f"   Пропущено (дубли): {skipped_count}")
        print(f"   Ошибки: {error_count}")
        print(f"{'=' * 80}")

        return 0 if added_count > 0 else 1

    finally:
        db.close()


if __name__ == "__main__":
    exit(main())