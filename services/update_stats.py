#!/usr/bin/env python3
"""Скрипт обновления статистики клиентов из 3x-ui API"""

import sys
import os
from datetime import datetime, timezone

# Добавляем корневую папку проекта в путь
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db_session, Client
from services.stats import XrayStatsService
from sqlalchemy import func
from config import XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD, XUI_WEB_BASE_PATH

# Инициализация сервиса статистики с конфигурацией из config.py
stats_service = XrayStatsService(
    panel_url=XUI_PANEL_URL,
    username=XUI_USERNAME,
    password=XUI_PASSWORD,
    web_base_path=XUI_WEB_BASE_PATH
)


def update_database():
    """Обновить статистику в БД"""
    db = get_db_session()
    try:
        # Получаем список email клиентов из 3x-ui API
        client_emails = stats_service.get_all_clients()

        if not client_emails:
            print("⚠️ Не найдено клиентов в 3x-ui API")
            print("💡 Подключитесь к VPN чтобы появилась статистика")
            return

        print(f"📊 Найдено клиентов в 3x-ui: {len(client_emails)}")

        updated_count = 0

        for email in client_emails:
            print(f"🔍 Обработка: {email}")

            # 🔥 email - это строка! Ищем клиента в БД
            client = db.query(Client).filter(Client.login == email).first()

            if not client:
                # Пробуем найти по full_name
                client = db.query(Client).filter(
                    func.lower(Client.full_name).contains(email.lower())
                ).first()

            if client:
                # 🔥 Получаем трафик из 3x-ui API (возвращает dict)
                traffic = stats_service.get_client_stats(email)

                # Инициализируем None значения
                if client.traffic_upload is None:
                    client.traffic_upload = 0
                if client.traffic_download is None:
                    client.traffic_download = 0
                if client.connection_count is None:
                    client.connection_count = 0

                # Обновляем статистику
                client.traffic_upload = max(client.traffic_upload, traffic.get('upload', 0))
                client.traffic_download = max(client.traffic_download, traffic.get('download', 0))
                client.last_seen = datetime.now(timezone.utc)
                client.is_online = True

                updated_count += 1
                print(
                    f"   ✅ {client.full_name}: "
                    f"↑{stats_service.format_bytes(traffic.get('upload', 0))} "
                    f"↓{stats_service.format_bytes(traffic.get('download', 0))}"
                )
            else:
                print(f"   ❌ Клиент '{email}' не найден в БД")

        db.commit()
        print(f"\n🎉 Обновлено {updated_count} клиентов")

        # Сбрасываем is_online для тех кто не был в 3x-ui
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
    print("🔄 Обновление статистики из 3x-ui API...")
    print(f"⏰ Время: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n")

    # Проверяем подключение к API
    print("🔍 Проверка подключения к Xray API...")
    if not stats_service.test_connection():
        print("❌ Не удалось подключиться к Xray API")
        print("💡 Проверьте что:")
        print("   • 3x-ui запущен (x-ui status)")
        print("   • Порт 2053 открыт")
        print("   • Логин/пароль правильные")
        return

    print("✅ Подключение к Xray API успешно!")

    # Обновляем БД
    update_database()


if __name__ == "__main__":
    main()