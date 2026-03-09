"""Автоматическая синхронизация клиентов Telegram с 3x-ui (Находит Inbound автоматически)"""

import sys
import os
import json
from sqlalchemy import inspect

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db_session, Client
from config import XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD, XUI_WEB_BASE_PATH, VLESS_PORT
import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

session_token = None


def login():
    """Вход в 3x-ui"""
    global session_token
    url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/login" if XUI_WEB_BASE_PATH else f"{XUI_PANEL_URL}/login"

    try:
        resp = requests.post(url, json={"username": XUI_USERNAME, "password": XUI_PASSWORD}, timeout=10)
        if resp.status_code == 200 and resp.json().get("success"):
            session_token = resp.cookies.get("3x-ui")
            logger.info("✅ Вход выполнен")
            return True
    except Exception as e:
        logger.error(f"Ошибка входа: {e}")
    return False


def get_inbound_by_port_or_name(port=None, name_keyword="VLESS"):
    """Ищет Inbound с нужным протоколом или именем"""
    url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/list"

    try:
        resp = requests.get(url, cookies={"3x-ui": session_token}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                for inbound in data.get("obj", []):
                    # Проверяем протокол или имя
                    proto = inbound.get("protocol", "").lower()
                    remark = inbound.get("remark", "").lower()

                    if port and inbound.get("port") == port:
                        logger.info(f"✅ Найден Inbound по порту {port}: ID={inbound.get('id')}")
                        return inbound.get("id")

                    if name_keyword.lower() in remark or proto == "vless":
                        logger.info(f"✅ Найден Inbound: {remark}, ID={inbound.get('id')}")
                        return inbound.get("id")

                # Если ничего не найдено, берем первый попавшийся валидный
                logger.warning(f"⚠️ Inbound по ключевым словам не найден, пробуем первый активный...")
                if data.get("obj"):
                    return data["obj"][0].get("id")
        logger.error("❌ Не удалось получить список Inbounds")
        return None
    except Exception as e:
        logger.error(f"Ошибка получения списка: {e}")
        return None


def get_existing_emails():
    """Получить существующие Email из панели"""
    emails = set()
    url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/list"
    try:
        resp = requests.get(url, cookies={"3x-ui": session_token}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                for inbound in data.get("obj", []):
                    settings_raw = inbound.get("settings", "{}")
                    if isinstance(settings_raw, str):
                        try:
                            settings = json.loads(settings_raw)
                            for client in settings.get("clients", []):
                                emails.add(client.get("email", "").lower())
                        except:
                            pass
    except Exception as e:
        logger.error(f"Ошибка чтения API: {e}")
    return emails


def add_clients(inbound_id, target_emails):
    """Добавить новые клиенты"""
    count = 0
    url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/addClient"

    for email in target_emails:
        # Формируем объект клиента
        client_data = {
            "email": email.split('@')[0],  # Используем часть до @ как логику
            "enabled": True,
            "expiryTime": 0,
            "totalGB": 0,
            "reset": 0,
            "tgId": "0",  # Пока заглушка
            "flow": ""
        }

        payload = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client_data]})
        }

        try:
            resp = requests.post(url, json=payload, headers={"Cookie": f"3x-ui={session_token}"}, timeout=10)
            if resp.status_code == 200 and resp.json().get("success"):
                count += 1
        except Exception as e:
            logger.error(f"Ошибка добавления {email}: {e}")

    return count


def main():
    print("=" * 70)
    print("🔄 Синхронизация клиентов Telegram с 3x-ui")
    print("=" * 70)

    if not login():
        return

    db = get_db_session()
    try:
        # 1. Получаем модель и поля
        cols = [c.name for c in inspect(Client).columns]
        print(f"[1] Поля модели: {cols[:5]}...")

        # 2. Ищем Inbound
        inbound_id = get_inbound_by_port_or_name(VLESS_PORT, "VLESS")
        if not inbound_id:
            logger.error("❌ Не найден Inbound для создания клиентов!")
            return

        # 3. Получаем существующие email
        existing = get_existing_emails()

        # 4. Собираем новых
        clients = db.query(Client).filter(Client.is_active == True).all()
        added_count = 0

        for c in clients:
            # Генерируем email из login (если email пустой)
            if hasattr(c, 'email') and c.email:
                email = c.email
            elif hasattr(c, 'login') and c.login:
                email = f"{c.login}@freeth.ru"
            else:
                email = f"user_{c.id}@freeth.ru"

            email_lower = email.lower()
            if email_lower in existing:
                continue

            # Добавляем
            if add_clients(inbound_id, [email]):
                added_count += 1
                print(f"✅ Добавлен: {email}")

        print(f"\n✅ Результат: Добавлено {added_count} новых клиентов")

    finally:
        db.close()


if __name__ == "__main__":
    main()