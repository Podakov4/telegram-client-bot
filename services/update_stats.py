#!/usr/bin/env python3
"""
Скрипт для обновления статистики из логов Xray
Запускается каждые 5 минут через cron
"""

import sys
import os
import subprocess
import re
from datetime import datetime

# 🔥 ВАЖНО: Добавляем корневую папку проекта в путь
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

print(f"📁 BASE_DIR: {BASE_DIR}")
print(f"📁 Current dir: {os.getcwd()}")
print(f"📁 Python path: {sys.path[:3]}")

# Теперь импортируем
try:
    from database import get_db_session, Client
    from sqlalchemy import func

    print("✅ Импорты успешны!")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print(f"📂 Проверяем файлы в {BASE_DIR}/database/")
    if os.path.exists(os.path.join(BASE_DIR, 'database')):
        print(f"   Files: {os.listdir(os.path.join(BASE_DIR, 'database'))}")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
def get_xray_logs():
    """Получить последние логи Xray"""
    try:
        # Увеличиваем таймаут до 30 секунд и берём меньше данных
        result = subprocess.run(
            ['sudo', 'journalctl', '-u', 'xray', '-n', '1000', '--no-pager'],
            capture_output=True,
            text=True,
            timeout=30  # Увеличили с 10 до 30 секунд
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        print("⚠️ Таймаут при получении логов (слишком много данных)")
        # Пробуем получить только последние 100 строк
        try:
            result = subprocess.run(
                ['sudo', 'journalctl', '-u', 'xray', '-n', '100', '--no-pager'],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout
        except:
            return ""
    except Exception as e:
        print(f"❌ Ошибка получения логов: {e}")
        return ""


def parse_traffic_from_logs(logs: str) -> dict:
    """
    Распарсить логи Xray
    Считаем подключения и последнюю активность
    """
    client_data = {}

    # Паттерн: email: client_X_name
    pattern = r'email:\s+(\S+)'

    for match in re.finditer(pattern, logs):
        email = match.group(1).rstrip('_k').rstrip('_Test')  # Убираем суффиксы

        if email not in client_data:
            client_data[email] = {
                'connections': 0,
                'last_seen': datetime.utcnow()
            }

        client_data[email]['connections'] += 1
        client_data[email]['last_seen'] = datetime.utcnow()

    return client_data


def update_database(client_data: dict):
    """Обновить статистику в БД"""
    db = get_db_session()

    try:
        updated_count = 0

        for email, data in client_data.items():
            print(f"🔍 Поиск клиента: {email}")

            # 🔥 Извлекаем ID из email (client_3_... → 3)
            client = None
            match = re.search(r'client_(\d+)', email)

            if match:
                client_id = int(match.group(1))
                client = db.query(Client).filter(Client.id == client_id).first()

                if client:
                    print(f"   ✅ Найден по ID: {client_id} → {client.full_name}")

            # Если не нашли по ID - пробуем по имени
            if not client:
                client = db.query(Client).filter(
                    func.lower(Client.full_name).contains(email.lower())
                ).first()

            if client:
                # Обновляем статистику
                client.last_seen = data['last_seen']
                if client.connection_count is None:
                    client.connection_count = 0
                client.connection_count += data['connections']

                # Тоже самое для трафика
                if client.traffic_upload is None:
                    client.traffic_upload = 0
                if client.traffic_download is None:
                    client.traffic_download = 0
                client.is_online = True
                updated_count += 1
                print(f"   ✅ {client.full_name}: +{data['connections']} подключений")
            else:
                print(f"   ❌ Не найден в БД")

        db.commit()
        print(f"\n🎉 Обновлено {updated_count} клиентов")

        # Сбрасываем is_online для тех кто не был в логах
        db.query(Client).update({Client.is_online: False})
        db.commit()

    except Exception as e:
        print(f"❌ Ошибка обновления БД: {e}")
        import traceback

        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


def main():
    print("🔄 Обновление статистики из логов Xray...")
    print(f"⏰ Время: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n")

    # Получаем логи
    logs = get_xray_logs()

    if not logs:
        print("⚠️ Логи пустые")
        return

    # Парсим трафик
    traffic_data = parse_traffic_from_logs(logs)

    if not traffic_data:
        print("⚠️ Не найдены данные о трафике")
        print("💡 Возможно, нужно включить логирование трафика в Xray")
        return

    print(f"📊 Найдено клиентов с трафиком: {len(traffic_data)}\n")

    # Обновляем БД
    update_database(traffic_data)


if __name__ == "__main__":
    main()
