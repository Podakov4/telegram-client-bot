#!/usr/bin/env python3
import requests
import json

api_url = "http://127.0.0.1:10085"

# Тест 1: Получение общей статистики
print("🔍 Тест 1: Общая статистика")
try:
    response = requests.post(
        f"{api_url}/service/StatsService.QueryStats",
        json={"pattern": "", "reset": False},
        timeout=5
    )
    print(f"✅ Статус: {response.status_code}")
    print(f"📊 Ответ: {json.dumps(response.json(), indent=2)[:500]}")
except Exception as e:
    print(f"❌ Ошибка: {e}")

# Тест 2: Статистика конкретного клиента
print("\n🔍 Тест 2: Статистика клиента client_3_podakov_k")
try:
    response = requests.post(
        f"{api_url}/service/StatsService.GetStats",
        json={"name": "user>>>client_3_podakov_k>>>traffic>>>uplink", "reset": False},
        timeout=5
    )
    print(f"✅ Статус: {response.status_code}")
    print(f"📊 Ответ: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"❌ Ошибка: {e}")

print("\n✅ Тесты завершены!")
