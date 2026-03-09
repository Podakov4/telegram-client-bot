"""Автоматическое добавление клиентов в 3x-ui с подробным дебаггингом"""

import sys
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db_session, Client
from config import XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD, XUI_WEB_BASE_PATH
import requests
import logging

# Настройка детального логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

session_token = None


def test_login_url(login_url):
    """Тестировать конкретный URL авторизации"""
    logger.debug(f"\n{'=' * 70}")
    logger.debug(f"🔍 ТЕСТУЕМ URL: {login_url}")
    logger.debug(f"{'=' * 70}")

    try:
        response = requests.post(
            login_url,
            json={"username": XUI_USERNAME, "password": XUI_PASSWORD},
            timeout=10
        )

        logger.info(f"   ✓ Код ответа: {response.status_code}")
        logger.info(f"   ✓ Заголовки: {dict(response.headers)}")
        logger.info(f"   ✓ Кукисы: {list(response.cookies.keys())}")
        logger.info(f"   ✓ Тело ответа (первые 200 символов):")
        logger.info(f"     {response.text[:200]}")

        # Проверяем успешность
        if response.status_code == 200:
            try:
                data = response.json()
                is_success = data.get("success", False)
                msg = data.get("msg", "")
                logger.info(f"   ✓ JSON success: {is_success}")
                logger.info(f"   ✓ JSON msg: {msg}")

                cookie_3xui = response.cookies.get("3x-ui") or response.cookies.get("session_name")
                if cookie_3xui:
                    logger.info(f"   ✅ НАЙДЕН ТОКЕН: {cookie_3xui[:30]}...")
                    return True, cookie_3xui
                else:
                    logger.warning("   ⚠️ Ответ 200, но токена нет!")
            except Exception as e:
                logger.error(f"   ❌ Ошибка парсинга JSON: {e}")
        elif response.status_code == 302:
            logger.warning("   ⚠️ Перенаправление (302)")
        else:
            logger.error(f"   ❌ HTTP код ошибки: {response.status_code}")

    except Exception as e:
        logger.error(f"   ❌ Исключение при запросе: {e}")

    return False, None


def find_auth_url():
    """Поиск правильного URL авторизации"""
    logger.info("=" * 70)
    logger.info("🔧 ПОИСК ПРАВИЛЬНОГО ПУТИ АВТОРИЗАЦИИ")
    logger.info("=" * 70)

    urls_to_test = []

    # Основные пути для тестирования
    base_urls = [
        f"{XUI_PANEL_URL}/panel/api/inbounds/list",
        f"{XUI_PANEL_URL}/panel/api/admin/login",
        f"{XUI_PANEL_URL}/panel/api/auth/login",
        f"{XUI_PANEL_URL}/api/auth/login",
        f"{XUI_PANEL_URL}/api/user/login",
        f"{XUI_PANEL_URL}/login",
        f"{XUI_PANEL_URL}/auth/login",
    ]

    # Если есть web base path, добавляем версии с ним
    if XUI_WEB_BASE_PATH:
        for base in base_urls:
            # Извлекаем домен и порт
            parts = base.replace(XUI_PANEL_URL, '').split('/')
            if len(parts) >= 1:
                remaining = '/'.join([p for p in parts[1:] if p])
                new_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/{remaining}"
                urls_to_test.append(new_url)
    else:
        urls_to_test = base_urls

    logger.info(f"\n📋 Будет протестировано {len(urls_to_test)} путей:")
    for i, url in enumerate(urls_to_test, 1):
        logger.info(f"   {i}. {url}")

    # Фильтруем только те что содержат "login" или "auth"
    auth_urls = [u for u in urls_to_test if "login" in u.lower() or "auth" in u.lower()]

    # Если ничего не нашлось, используем все как fallback
    if not auth_urls:
        auth_urls = urls_to_test

    for url in auth_urls:
        logger.info(f"\n🧪 Тест URL #{auth_urls.index(url) + 1}:")
        is_success, token = test_login_url(url)
        if is_success:
            logger.info(f"\n✅ Найдено рабочее автоизационное URL: {url}")
            return url, token

    logger.critical("\n❌ НЕ УДАЛОСЬ НАЙТИ РАБОЧИЙ URL АВТОРИЗАЦИИ!")
    logger.critical("Проверьте настройки в .env файле и доступность панели 3x-ui")
    return None, None


def add_client_to_inbound(inbound_id, email, tg_id):
    """Добавить клиента в inbound"""
    try:
        # Пробуем несколько вариантов URL
        test_urls = [
            f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/addClient",
            f"{XUI_PANEL_URL}/panel/api/inbounds/addClient",
        ]

        success = False
        for url in test_urls:
            client_data = {
                "email": email,
                "enabled": True,
                "expiryTime": 0,
                "totalGB": 0,
                "reset": 0,
                "tgId": str(tg_id),
                "flow": ""
            }

            payload = {
                "id": inbound_id,
                "settings": json.dumps({
                    "clients": [client_data]
                })
            }

            headers = {"Cookie": f"3x-ui={session_token}"}
            response = requests.post(url, json=payload, headers=headers, timeout=30)

            logger.info(f"   📩 URL: {url}")
            logger.info(f"   ✉️ Ответ: {response.status_code} {response.text[:200]}")

            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    logger.info(f"   ✅ Клиент успешно добавлен!")
                    success = True
                    break

        return success

    except Exception as e:
        logger.error(f"❌ Ошибка создания клиента '{email}': {e}")
        return False


def main():
    print("=" * 80)
    print("🔄 ДОБАВЛЕНИЕ КЛИЕНТОВ В 3x-ui (ДЕБАГГИНГ)")
    print("=" * 80)

    # 1. Поиск рабочего URL
    auth_url, token = find_auth_url()

    if not auth_url:
        return 1

    global session_token
    session_token = token

    db = get_db_session()
    try:
        # 2. Получаем клиентов
        target_clients = db.query(Client).filter(
            Client.is_active == True,
            Client.email == None,
            ~Client.login.in_(['', None])
        ).all()

        logger.info(f"\n[1] Найдено клиентов для добавления: {len(target_clients)}")

        for c in target_clients:
            logger.info(f"   - {c.full_name} ({c.telegram_id}) → {c.login}")

        # 3. Получаем существующих из API
        existing_emails = set()
        list_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/list"
        resp = requests.get(list_url, cookies={"3x-ui": session_token})

        logger.info(f"\n[2] Проверка списка клиентов API...")
        logger.info(f"   URL: {list_url}")
        logger.info(f"   Status: {resp.status_code}")

        if resp.status_code == 200:
            try:
                data = resp.json()
                logger.info(f"   JSON: {data}")
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
            except Exception as e:
                logger.error(f"❌ Ошибка парсинга списка: {e}")
                logger.error(f"Текст ответа: {resp.text[:500]}")
        else:
            logger.error(f"Ошибка получения списка: {resp.status_code}")
            logger.error(f"Ответ: {resp.text[:500]}")

        logger.info(f"\n[3] Клиентов уже в панели: {len(existing_emails)}")

        # 4. Добавляем новых
        added_count = 0
        skipped_count = 0
        error_count = 0
        inbound_id = 2

        logger.info(f"\n💾 Начинаем добавление в inbound #{inbound_id}...\n")

        for c in target_clients:
            if c.login:
                email = f"{c.login}@freeth.ru"
            else:
                email = f"user_{c.id}@freeth.ru"

            tg_id = c.telegram_id

            if email.lower() in existing_emails:
                logger.info(f"⏸️ Пропущен (уже в API): {email}")
                skipped_count += 1
                continue

            success = add_client_to_inbound(inbound_id, email, tg_id)

            if success:
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