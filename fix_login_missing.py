"""Автоматическое добавление клиентов в 3x-ui (ИСПРАВЛЕНО)"""

import sys
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db_session, Client
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
    """Авторизация в 3x-ui"""
    global session_token
    
    # 🔥 ИСПРАВЛЕНО: правильный путь /login вместо /panel/api/admin/login
    if XUI_WEB_BASE_PATH:
        login_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/login"
    else:
        login_url = f"{XUI_PANEL_URL}/login"
    
    logger.info(f"🔑 Попытка входа в {login_url}")
    
    response = requests.post(
        login_url,
        json={"username": XUI_USERNAME, "password": XUI_PASSWORD},
        timeout=10
    )
    
    logger.info(f"   ✍️ Ответ сервера: код {response.status_code}")
    
    if response.status_code == 200:
        try:
            data = response.json()
            logger.info(f"   📄 JSON: {data}")
            
            if data.get("success"):
                session_token = response.cookies.get("3x-ui")
                logger.info("✅ Авторизация успешна!")
                return True
            else:
                logger.error(f"❌ Ошибка: {data.get('msg', 'Unknown')}")
        except Exception as e:
            logger.error(f"❌ JSON парсинг: {e}")
            return False
    
    logger.error(f"❌ HTTP ошибка: {response.status_code}")
    return False


def add_client_to_inbound(inbound_id, email, tg_id):
    """Добавить клиента в inbound"""
    try:
        # Пробуем оба варианта URL
        test_urls = [
            f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/addClient",
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
        
        payload = {
            "id": inbound_id,
            "settings": json.dumps({
                "clients": [client_data]
            })
        }
        
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
        logger.error(f"❌ Ошибка создания: {e}")
        return False


def main():
    print("=" * 80)
    print("🔄 ДОБАВЛЕНИЕ КЛИЕНТОВ В 3x-ui (ИСПРАВЛЕНО)")
    print("=" * 80)
    
    # 1. Авторизация
    if not login():
        logger.critical("Не удалось авторизоваться!")
        return 1
    
    db = get_db_session()
    try:
        # 2. Получаем активных клиентов с пустым email
        target_clients = db.query(Client).filter(
            Client.is_active == True,
            # Проверяем наличие email или login
            ~(Client.email.is_(None) & Client.login.is_(None))
        ).all()
        
        logger.info(f"\n[1] Найдено для добавления: {len(target_clients)}")
        for c in target_clients:
            logger.info(f"   - {c.full_name or 'Без имени'} ({c.telegram_id}) → login={c.login}, email={c.email}")
        
        # 3. Получаем существующих из API
        existing_emails = set()
        if XUI_WEB_BASE_PATH:
            list_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/list"
        else:
            list_url = f"{XUI_PANEL_URL}/panel/api/inbounds/list"
        
        resp = requests.get(list_url, cookies={"3x-ui": session_token})
        
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
                
                logger.info(f"\n[2] Клиентов в API уже есть: {count}")
            else:
                logger.error(f"API ответ: {data.get('msg')}")
        else:
            logger.error(f"Ошибка получения списка: {resp.status_code}")
        
        # 4. Добавляем новых
        added_count = 0
        skipped_count = 0
        inbound_id = 2  # VLESS через Nginx (из проверки)
        
        logger.info(f"\n💾 Начинаем добавление...\n")
        
        for c in target_clients:
            # Строим email из login если email пустой
            if c.email:
                email = c.email
            elif c.login:
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
                # Обновляем email в БД если был пустой
                if not c.email:
                    c.email = email
                added_count += 1
                logger.info(f"✅ Добавлен: {email}\n")
            else:
                logger.error(f"❌ Ошибка: {email}\n")
        
        db.commit()
        
        print(f"\n{'='*80}")
        print(f"📊 РЕЗУЛЬТАТЫ:")
        print(f"   Успешно создано: {added_count}")
        print(f"   Пропущено (дубли): {skipped_count}")
        print(f"{'='*80}")
        
        return 0 if added_count > 0 else 1
        
    finally:
        db.close()


if __name__ == "__main__":
    exit(main())