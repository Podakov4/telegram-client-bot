#!/usr/bin/env python3
"""Скрипт добавления клиентов в 3x-ui (исправлено под схему с NULL email)"""

import sys
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db_session, Client
from config import XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD, XUI_WEB_BASE_PATH
import requests
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

session_token = None


def login():
    """Авторизация в 3x-ui"""
    global session_token

    # Правильное построение URL
    if XUI_WEB_BASE_PATH:
        login_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/admin/login"
    else:
        login_url = f"{XUI_PANEL_URL}/panel/api/admin/login"

    logger.info(f"🔑 Попытка входа в {login_url}")
    logger.info(f"   Username: {XUI_USERNAME}")
    logger.info(f"   Password: {'*' * len(XUI_PASSWORD)}")
    logger.info(f"   Web Path: {XUI_WEB_BASE_PATH or 'None'}")

    response = requests.post(
        login_url,
        json={"username": XUI_USERNAME, "password": XUI_PASSWORD},
        timeout=10
    )

    logger.info(f"   Ответ сервера: код {response.status_code}")

    if response.status_code == 200:
        try:
            data = response.json()
            logger.info(f"   Тело ответа: {data}")

            if data.get("success"):
                session_token = response.cookies.get("3x-ui")
                logger.info("✅ Авторизация в 3x-ui успешна!")
                return True
            else:
                logger.error(f"❌ Ошибка авторизации: {data.get('msg', 'Unknown error')}")
                return False
        except Exception as e:
            logger.error(f"❌ Не удалось распарсить JSON: {e}")
            logger.error(f"Текст ответа: {response.text[:500]}")
            return False
    else:
        logger.error(f"❌ HTTP ошибка: {response.status_code}")
        logger.error(f"Текст ошибки: {response.text[:500]}")

        # Пробуем альтернативный путь авторизации
        if XUI_WEB_BASE_PATH:
            alt_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/api/user/login"
        else:
            alt_url = f"{XUI_PANEL_URL}/api/user/login"

        logger.info(f"⚠️ Пробуем альтернативный путь: {alt_url}")
        response_alt = requests.post(alt_url, json={"username": XUI_USERNAME, "password": XUI_PASSWORD}, timeout=10)

        if response_alt.status_code == 200 and response_alt.json().get("success"):
            session_token = response_alt.cookies.get("3x-ui")
            if session_token:
                logger.info("✅ Альтернативная авторизация успешна!")
                return True

    logger.critical("Невозможно продолжить без авторизации!")
    return False


def add_client_to_inbound(inbound_id, email, tg_id):
    """Добавление клиента в конкретный инбоуд"""
    try:
        if XUI_WEB_BASE_PATH:
            url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/addClient"
        else:
            url = f"{XUI_PANEL_URL}/panel/api/inbounds/addClient"

        logger.info(f"📩 Отправка запроса на: {url}")

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

        logger.info(f"   Код ответа: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                return True

        logger.warning(f"⚠️ Не удалось создать {email}: {response.text[:200]}")
        return False

    except Exception as e:
        logger.error(f"❌ Ошибка создания {email}: {e}")
        return False


def main():
    print("=" * 80)
    print("🔄 ДОБАВЛЕНИЕ КЛИЕНТОВ В 3x-ui (ИСПРАВЛЕНО)")
    print("=" * 80)

    # 1. Вход в систему
    if not login():
        logger.critical("Невозможно продолжить без авторизации!")
        return 1

    db = get_db_session()
    try:
        # 2. Получаем активных клиентов с пустым email, но имеющим login
        target_clients = db.query(Client).filter(
            Client.is_active == True,
            Client.email == None,  # Проверка именно на NULL
            ~Client.login.in_(['', None])
        ).all()

        logger.info(f"[1] Найдено клиентов для добавления: {len(target_clients)}")

        for c in target_clients:
            logger.info(f"   - {c.full_name} ({c.telegram_id}) → {c.login}")

        # Получаем список существующих email из панели, чтобы избежать дублей
        existing_emails = set()
        list_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/list"
        resp = requests.get(list_url, cookies={"3x-ui": session_token})

        logger.info(f"\n[2] Получаем список существующих клиентов из API...")

        if resp.status_code == 200:
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
                            existing_emails.add(email.lower())
                            count += 1

                logger.info(f"      Успешно получено {count} клиентов")
            else:
                logger.error(f"Ошибка API: {data.get('msg', 'Unknown error')}")
        else:
            logger.error(f"Ошибка получения списка: {resp.status_code}")

        logger.info(f"\n[3] Клиентов уже в панели: {len(existing_emails)}")

        # Идём по списку и добавляем
        added_count = 0
        skipped_count = 0
        error_count = 0

        # Инбоуд #2 соответствует VLESS через Nginx (проверено ранее)
        inbound_id = 2

        logger.info(f"\n💾 Начинаем добавление в inbound #{inbound_id}...\n")

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
                logger.info(f"✅ Добавлен: {email}\n")
            else:
                error_count += 1
                logger.error(f"❌ Ошибка: {email}\n")

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