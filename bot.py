#!/usr/bin/env python3
"""Принудительное добавление клиентов в 3x-ui без проверок"""

import sys
import os
import json
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# Импорт настроек
from config import XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD, XUI_WEB_BASE_PATH, VLESS_PORT, VLESS_PATH

# Импорт базы данных
from database import get_db_session, Client
import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === ИНИЦИАЛИЗАЦИЯ API ===

session = None
login_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/login" if XUI_WEB_BASE_PATH else f"{XUI_PANEL_URL}/login"


def login_xui():
    global session
    response = requests.post(login_url, json={"username": XUI_USERNAME, "password": XUI_PASSWORD})
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            cookies = {"3x-ui": response.cookies.get("3x-ui")}
            logger.info("✅ Авторизация в 3x-ui успешна")
            return cookies
    logger.error(f"❌ Ошибка входа: {response.status_code}")
    return None


def add_client_to_inbound(inbound_id, email, tg_id=None):
    """Добавить клиента через прямой POST запрос к API addClient"""

    # Пытаемся найти порт для конкретного инбоуда
    url_list = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/list"
    resp = requests.get(url_list, cookies=session, timeout=10)

    if resp.status_code != 200:
        logger.error(f"Не удалось получить список инбаундов: {resp.status_code}")
        return False

    data = resp.json()
    if not data.get("success"):
        logger.error(f"Ошибка получения списка: {data}")
        return False

    target_id = None

    # Находим правильный INBOUND по порту или имени
    for inbound in data.get("obj", []):
        pid = inbound.get("port")
        if pid == VLESS_PORT:
            target_id = inbound.get("id")
            break

    if not target_id:
        logger.warning("Инбоуд по порту 443 не найден, пробуем первый попавшийся VLESS...")
        # Fallback: берем любой с протоколом vless
        for inbound in data.get("obj", []):
            if inbound.get("protocol").lower() == "vless":
                target_id = inbound.get("id")
                break

    if not target_id:
        logger.critical("❌ Не удалось найти корректный Inbound!")
        return False

    logger.info(f"Найдена цель для добавления: Inbound ID={target_id}, Порт={VLESS_PORT}")

    # Формируем JSON для addClient (стандартная структура 3x-ui)
    client_settings = {
        "clients": [
            {
                "email": email,
                "enabled": True,
                "expiryTime": 0,  # Без ограничений по времени
                "totalGB": 0,  # Безлимитный трафик
                "reset": 0,  # Бессрочный счетчик трафика
                "tgId": str(tg_id) if tg_id else "",  # Привязка к Telegram
                "flow": ""  # Обычный VLESS без обфускации
            }
        ]
    }

    add_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/addClient"

    try:
        req_payload = {
            "id": int(target_id),  # Обязательно преобразуем в INT
            "settings": json.dumps(client_settings["clients"]),  # Передаем массив как строку JSON
            "forceEnable": True
        }

        # ВАЖНО: передаем данные как JSON объект, а не словарь внутри словаря
        response = requests.post(
            add_url,
            json=req_payload,
            cookies=session,
            timeout=30
        )

        result = response.json()
        if result.get("success"):
            logger.info(f"✅ Клиент {email} успешно создан!")
            return True
        else:
            logger.error(f"⚠️ Ответ API: {result.get('msg', 'Unknown')}")
            return False

    except Exception as e:
        logger.error(f"❌ Ошибка при создании клиента {email}: {e}")
        return False


def main():
    print("=" * 80)
    print("🔄 ПРИНУДИТЕЛЬНОЕ ДОБАВЛЕНИЕ КЛИЕНТОВ В PANEL")
    print("=" * 80)

    if not login_xui():
        return 1

    db = get_db_session()
    try:
        # Получаем ВСХ активные клиенты
        clients = db.query(Client).filter(Client.is_active == True).all()

        logger.info(f"\n[1] Найдено {len(clients)} активных клиентов в базе:\n")

        for c in clients:
            # Генерируем email из login
            email = f"{c.login}@freeth.ru" if c.login else f"user_{c.id}@freeth.ru"

            # Проверяем есть ли уже ссылка в БД
            has_sub = c.subscription_link is not None and len(str(c.subscription_link)) > 0

            # Считаем его клиентом если нет ссылки или мы хотим пересоздать
            logger.info(f"- {c.full_name or 'Без имени'} ({c.telegram_id}) → Email: {email}")
            logger.info(f"  Подписка в БД: {'✅ Есть' if has_sub else '❌ Нет'}")

            # Добавляем в панель (снова, даже если была ошибка ранее)
            success = add_client_to_inbound(None, email, c.telegram_id)

            if success:
                if not has_sub:
                    # Обновляем БД ссылкой
                    new_link = f"https://freeth.ru{VLESS_PATH}?encryption=none&security=tls&sni=freeth.ru&type=ws&path=%2Fvless&host=freeth.ru"
                    c.subscription_link = new_link

                db.commit()
                logger.info(f"   Результат: ✅ Успешно обновлено!")
            else:
                logger.error(f"   Результат: ❌ Ошибка создания")

        print(f"\n{'=' * 80}")
        print("📊 ЗАВЕРШЕНИЕ:")
        print("После этого зайдите в панель 3x-ui и проверьте вкладку 'Clients' у соответствующего Inbound.")
        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    exit(main())