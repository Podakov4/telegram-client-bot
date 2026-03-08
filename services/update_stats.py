import sys
import os
import re
from datetime import datetime, timezone

# Добавляем корневую папку проекта в путь
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db_session, Client
from services.stats import XrayStatsService
from sqlalchemy import func

stats_service = XrayStatsService()


def get_clients_from_xray() -> list:
    """Получить список всех клиентов из Xray API"""
    all_stats = stats_service.get_all_stats()

    clients = []
    if 'stat' in all_stats:
        for stat in all_stats['stat']:
            name = stat.get('name', '')
            # Извлекаем email из имени статистики
            # Формат: user>>>email>>>traffic>>>uplink/downlink
            match = re.search(r'user>>>(\S+)>>>traffic', name)
            if match:
                email = match.group(1)
                if email not in clients:
                    clients.append(email)

    return clients


def get_client_traffic(email: str) -> dict:
    """Получить трафик для конкретного клиента"""
    return stats_service.get_client_stats(email)


def update_database():
    """Обновить статистику в БД"""
    db = get_db_session()

    try:
        # Получаем всех клиентов из Xray
        xray_clients = get_clients_from_xray()

        if not xray_clients:
            print("⚠️ Не найдено клиентов в Xray API")
            print("💡 Подключитесь к VPN чтобы появилась статистика")
            return

        print(f"📊 Найдено клиентов в Xray: {len(xray_clients)}")

        updated_count = 0

        for email in xray_clients:
            print(f"🔍 Обработка: {email}")

            # Извлекаем ID из email (client_3_... → 3)
            client = None
            match = re.search(r'client_(\d+)', email)

            if match:
                client_id = int(match.group(1))
                client = db.query(Client).filter(Client.id == client_id).first()

                if client:
                    print(f"   ✅ Найден по ID: {client_id} → {client.full_name}")

            if not client:
                # Пробуем найти по имени
                client = db.query(Client).filter(
                    func.lower(Client.full_name).contains(email.lower())
                ).first()

            if client:
                # Получаем трафик из Xray API
                traffic = get_client_traffic(email)

                # Инициализируем None значения
                if client.traffic_upload is None:
                    client.traffic_upload = 0
                if client.traffic_download is None:
                    client.traffic_download = 0
                if client.connection_count is None:
                    client.connection_count = 0

                # Обновляем статистику
                # Xray возвращает общие значения (накопленные с момента запуска)
                # Поэтому берём максимальное значение
                client.traffic_upload = max(client.traffic_upload, traffic.get('upload', 0))
                client.traffic_download = max(client.traffic_download, traffic.get('download', 0))
                client.last_seen = datetime.now(timezone.utc)
                client.is_online = True
                client.connection_count += 1

                updated_count += 1
                print(
                    f"   ✅ {client.full_name}: ↑{stats_service.format_bytes(traffic.get('upload', 0))} ↓{stats_service.format_bytes(traffic.get('download', 0))}")
            else:
                print(f"   ❌ Клиент '{email}' не найден в БД")

        db.commit()
        print(f"\n🎉 Обновлено {updated_count} клиентов")

        # Сбрасываем is_online для тех кто не был в Xray
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
    print("🔄 Обновление статистики из Xray API...")
    print(f"⏰ Время: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n")

    # Проверяем подключение к API
    print("🔍 Проверка подключения к Xray API...")
    if not stats_service.test_connection():
        print("❌ Не удалось подключиться к Xray API")
        print("💡 Проверьте что:")
        print("   • Xray запущен (sudo systemctl status xray)")
        print("   • API порт 10085 открыт (sudo ss -tlnp | grep 10085)")
        print("   • В конфиге Xray есть секция api")
        return

    print("✅ Подключение к Xray API успешно!")

    # Обновляем БД
    update_database()


if __name__ == "__main__":
    main()
