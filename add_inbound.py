import requests
import json
import uuid

panel_url = "http://72.56.118.169:2053"
web_base_path = "YFBFh5UWZXQ7YxG6lt"
username = "xCwgwlzm8x"
password = "JOc8S87g30"

# Логин
login_url = f"{panel_url}/{web_base_path}/login"
response = requests.post(
    login_url,
    json={"username": username, "password": password},
    timeout=10
)

if response.status_code == 200 and response.json().get("success"):
    session = response.cookies.get("3x-ui")
    print(f"✅ Успешный вход!")

    # Генерируем новый UUID для клиента
    client_id = str(uuid.uuid4())
    print(f"🔑 Новый UUID: {client_id}")

    # Правильная структура - БЕЗ json.dumps()
    inbound_data = {
        "up": 0,
        "down": 0,
        "total": 0,
        "remark": "VLESS WebSocket",
        "enable": True,
        "expiryTime": 0,
        "listen": "",
        "port": 443,
        "protocol": "vless",
        "settings": {
            "clients": [
                {
                    "id": client_id,
                    "email": "client_3_podakov_k",
                    "level": 0,
                    "flow": "",
                    "subId": ""
                }
            ],
            "decryption": "none"
        },
        "streamSettings": {
            "network": "ws",
            "security": "none",
            "wsSettings": {
                "path": "/vless",
                "headers": {
                    "Host": ""
                }
            }
        },
        "sniffing": {
            "enabled": True,
            "destOverride": ["http", "tls"]
        },
        "tag": f"vless-ws-443-{client_id[:8]}"
    }

    # Добавляем inbound
    api_url = f"{panel_url}/{web_base_path}/panel/api/inbounds/add"
    response = requests.post(
        api_url,
        json=inbound_data,
        cookies={"3x-ui": session},
        timeout=10
    )

    print(f"\n📊 Response: {response.status_code}")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            print("\n✅ Inbound успешно добавлен!")
            print(f"📧 Email: client_3_podakov_k")
            print(f"🔑 UUID: {client_id}")
            print(f"🌐 Port: 443")
            print(f"📡 Path: /vless")
        else:
            print(f"\n⚠️ Ответ API: {data.get('msg', 'Unknown')}")
    else:
        print(f"\n❌ HTTP ошибка: {response.status_code}")
else:
    print("❌ Ошибка входа")