#!/usr/bin/env python3
"""
Скрипт для обновления статистики из логов Xray
Запускается каждые 5 минут через cron
"""

import subprocess
import re
from datetime import datetime
from database import get_db_session, Client
from sqlalchemy import func


def get_xray_logs():
    """Получить последние логи Xray"""
    try:
        result = subprocess.run(
            ['sudo', 'journalctl', '-u', 'xray', '--since', '5 minutes ago', '--no-pager'],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout
    except Exception as e:
        print(f"❌ Ошибка получения логов: {e}")
        return ""


def parse_traffic_from_logs(logs: str) -> dict:
    """
    Распарсить трафик из логов
    Возвращает: {'email': {'upload': bytes, 'download': bytes}}
    """
    traffic_data = {}

    # Паттерн: email traffic: uplink=X downlink=Y
    pattern = r'(\S+)\s+traffic:\s+uplink=(\d+)\s+downlink=(\d+)'

    for match in re.finditer(pattern, logs):
        email = match.group(1)
        uplink = int(match.group(2))
        downlink = int(match.group(3))

        if email not in traffic_data:
            traffic_data[email] = {'upload': 0, 'download': 0}

        # Накапливаем трафик
        traffic_data[email]['upload'] += uplink
        traffic_data[email]['download'] += downlink

    return traffic_data


def update_database(traffic_data: dict):
    """Обновить статистику в БД"""
    db = get_db_session()

    try:
        updated_count = 0

        for email, stats in traffic_data.items():
            # Ищем клиента по email (UUID в wireguard_public_key)
            # Или по части email (client_X_name)
            client = db.query(Client).filter(
                func.lower(Client.full_name).contains(email.lower())
            ).first()

            if not client:
                # Пробуем найти по username
                client = db.query(Client).filter(
                    func.lower(Client.username).contains(email.lower())
                ).first()

            if client:
                # Обновляем трафик (накапливаем)
                client.traffic_upload += stats['upload']
                client.traffic_download += stats['download']
                client.last_seen = datetime.utcnow()
                client.connection_count += 1
                updated_count += 1
                print(f"✅ {client.full_name}: ↑{stats['upload']} ↓{stats['download']}")

        db.commit()
        print(f"\n🎉 Обновлено {updated_count} клиентов")

    except Exception as e:
        print(f"❌ Ошибка обновления БД: {e}")
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