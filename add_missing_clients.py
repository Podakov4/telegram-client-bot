"""Принудительное добавление всех клиентов в панель без проверок"""

import sys
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db_session, Client
import requests
from config import XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD, XUI_WEB_BASE_PATH
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 🔥 ИСПРАВЛЕНО: порт из панели (не из конфига!)
INBOUND_ID_TO_USE = 2  # Это подтверждено твоим скриптом


def main():
    print("=" * 80)
    print("🔄 ДОБАВЛЕНИЕ ВСЕХ КЛИЕНТОВ ПРИНУДИТЕЛЬНО")
    print("=" * 80)
    
    # 1. Авторизация
    login_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/login" if XUI_WEB_BASE_PATH else f"{XUI_PANEL_URL}/login"
    logger.info(f"🔑 Попытка входа: {login_url}")
    
    resp_login = requests.post(login_url, json={"username": XUI_USERNAME, "password": XUI_PASSWORD}, timeout=10)
    
    if resp_login.status_code == 200:
        data = resp_login.json()
        if data.get("success"):
            session_token = resp_login.cookies.get("3x-ui")
            logger.info("✅ Авторизация успешна!")
        else:
            logger.error(f"❌ Ошибка входа: {data.get('msg')}")
            return 1
    else:
        logger.error(f"❌ HTTP ошибка: {resp_login.status_code}")
        return 1
    
    session = {"3x-ui": session_token}
    
    # 2. Проверка существующих email в API
    list_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/list"
    resp_list = requests.get(list_url, cookies=session, timeout=10)
    
    if resp_list.status_code != 200:
        logger.error(f"❌ Ошибка получения списка: {resp_list.status_code}")
        return 1
        
    data_list = resp_list.json()
    existing_emails = set()
    
    if data_list.get("success"):
        for inbound in data_list.get("obj", []):
            if inbound.get("id") == INBOUND_ID_TO_USE:
                settings_raw = inbound.get("settings", "{}")
                if isinstance(settings_raw, str):
                    try:
                        settings = json.loads(settings_raw)
                        for client in settings.get("clients", []):
                            email = client.get("email", "")
                            if email:
                                existing_emails.add(email.lower())
                                logger.info(f"📋 Существующий клиент в API: {email}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось распарсить настройки: {e}")
    else:
        logger.error(f"❌ Ошибка ответа API: {data_list.get('msg')}")
        
    db = get_db_session()
    try:
        # 3. Получаем всех активных клиентов из БД
        clients = db.query(Client).filter(Client.is_active == True).all()
        
        logger.info(f"\n[1] Найдено {len(clients)} активных клиентов в базе:\n")
        
        for c in clients:
            logger.info(f"- {c.full_name or 'Без имени'} ({c.telegram_id})")
            logger.info(f"   Login: {c.login}")
        
        # 4. Добавляем недостающих клиентов
        url_add = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/addClient"
        added_count = 0
        skipped_count = 0
        
        for c in clients:
            # Генерируем email из login
            if c.login:
                email = f"{c.login}@freeth.ru"
            else:
                email = f"user_{c.id}@freeth.ru"
            
            email_lower = email.lower()
            
            # Проверяем есть ли уже такой клиент
            if email_lower in existing_emails:
                logger.info(f"⏸️ Пропущен (уже есть в API): {email}")
                skipped_count += 1
                continue
            
            # Формируем JSON для addClient
            # ВАЖНО: В 3x-ui нужна правильная структура!
            client_data = {
                "email": email,
                "enabled": True,
                "expiryTime": 0,           # Бессрочно
                "totalGB": 0,              # Безлимит
                "reset": 0,                # Бессрочный трафик
                "tgId": str(c.telegram_id),
                "flow": ""                 # Обычный поток
            }
            
            payload = {
                "id": INBOUND_ID_TO_USE,
                "settings": json.dumps({"clients": [client_data]}),
                "forceEnable": True
            }
            
            logger.info(f"📩 Отправка запроса для {email}:")
            logger.info(f"   Payload: {json.dumps(payload, indent=2)[:200]}...")
            
            resp_add = requests.post(url_add, json=payload, cookies=session, timeout=30)
            
            if resp_add.status_code == 200:
                result = resp_add.json()
                if result.get("success"):
                    logger.info(f"✅ Успешно добавлен: {email}")
                    added_count += 1
                    
                    # Обновляем в БД ссылку на подписку (если нужно)
                    c.subscription_link = f"https://freeth.ru/vless?encryption=none&security=tls&sni=freeth.ru&type=ws&path=%2Fvless&host=freeth.ru"
                else:
                    logger.error(f"❌ Ошибка от API: {result.get('msg')}")
                    logger.error(f"   Полный ответ: {result}")
            else:
                logger.error(f"❌ HTTP ошибка: {resp_add.status_code}")
                logger.error(f"   Текст ответа: {resp_add.text[:500]}")
        
        db.commit()
        
        print(f"\n{'='*80}")
        print(f"📊 РЕЗУЛЬТАТЫ:")
        print(f"   Добавлено новых: {added_count}")
        print(f"   Пропущено (дубли): {skipped_count}")
        print(f"   Всего обработано: {len(clients)}")
        print(f"{'='*80}")
        
        if added_count == 0:
            logger.warning("⚠️ Ничего не добавлено! Возможно все клиенты уже есть.")
            return 1
        else:
            logger.info("✅ Готово! Зайдите в панель и проверьте список клиентов.")
            return 0
            
    finally:
        db.close()


if __name__ == "__main__":
    exit(main())