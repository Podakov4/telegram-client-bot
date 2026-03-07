#!/usr/bin/env python3
import sys
sys.path.insert(0, '/root/bot_telegram/telegram-client-bot')

import config
from services.vless import VLESSManager

print(f"🔍 VLESS_PORT из config: {config.VLESS_PORT}")

manager = VLESSManager(
    server_ip=config.WG_SERVER_IP,
    port=config.VLESS_PORT,  # Должно быть 443
    path=config.VLESS_PATH,
    host="freeth.ru"
)

uuid, link = manager.add_client_to_xray(None, 999, "Test")
print(f"🔗 Сгенерированная ссылка:\n{link}")

# Проверка что порт 443
if ":443?" in link:
    print("✅ Порт 443 в ссылке!")
else:
    print("❌ Порт НЕ 443!")