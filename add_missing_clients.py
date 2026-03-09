"""Добавляем клиентов вручную через API"""

import sys, os, json
sys.path.insert(0, "/root/bot_telegram/telegram-client-bot")

from database import get_db_session, Client
import requests
from config import XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD, XUI_WEB_BASE_PATH

# Авторизация
login_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/login"
resp = requests.post(login_url, json={"username": XUI_USERNAME, "password": XUI_PASSWORD})
token = resp.cookies.get("3x-ui") if resp.status_code == 200 else None

print(f"🔑 Авторизация: {'✅ Успех' if token else '❌ Ошибка'}")

db = get_db_session()
try:
    # Находим Inbound с портом 10443 (или любым vless)
    list_url = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/list"
    data = requests.get(list_url, cookies={"3x-ui": token}).json()
    
    inbound_id = None
    for inbound in data["obj"] if data.get("success") else []:
        if inbound.get("port") == 10443 or inbound.get("protocol") == "vless":
            inbound_id = inbound.get("id")
            break
    
    print(f"📍 Inbound ID для добавления: {inbound_id}")
    
    # Добавляем клиентов
    clients_to_add = db.query(Client).filter(
        Client.is_active == True, 
        ~Client.login.in_(["client_3_podakov_k"])  # Исключаем уже существующего
    ).all()
    
    added = 0
    url_add = f"{XUI_PANEL_URL}/{XUI_WEB_BASE_PATH}/panel/api/inbounds/addClient"
    
    for c in clients_to_add:
        email = f"{c.login}@freeth.ru"
        
        payload = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [
                {
                    "email": email,
                    "enabled": True,
                    "expiryTime": 0,
                    "totalGB": 0,
                    "reset": 0,
                    "tgId": str(c.telegram_id),
                    "flow": ""
                }
            ]})
        }
        
        res = requests.post(url_add, json=payload, cookies={"3x-ui": token})
        
        if res.json().get("success"):
            print(f"✅ Добавлен: {email}")
            added += 1
        
    print(f"\n🎉 Итого добавлено: {added}")
finally:
    db.close()