# services/stats.py
import grpc
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict


class XrayStatsService:
    """Сервис для получения статистики из Xray API через HTTP/JSON"""

    def __init__(self, api_url: str = "127.0.0.1:10085"):
        self.api_url = api_url

    def connect(self) -> bool:
        """Проверка подключения к API"""
        try:
            import requests
            response = requests.post(
                f"http://{self.api_url}/service/StatsService.QueryStats",
                json={"pattern": "", "reset": False},
                timeout=5
            )
            return response.status_code == 200
        except:
            return False

    def get_client_stats(self, email: str) -> dict:
        """Получить статистику по клиенту"""
        try:
            import requests

            # Запрос для uplink
            uplink_response = requests.post(
                f"http://{self.api_url}/service/StatsService.GetStats",
                json={"name": f"user>>>{email}>>>traffic>>>uplink", "reset": False},
                timeout=5
            )

            # Запрос для downlink
            downlink_response = requests.post(
                f"http://{self.api_url}/service/StatsService.GetStats",
                json={"name": f"user>>>{email}>>>traffic>>>downlink", "reset": False},
                timeout=5
            )

            upload = 0
            download = 0

            if uplink_response.status_code == 200:
                data = uplink_response.json()
                upload = data.get("stat", {}).get("value", 0)

            if downlink_response.status_code == 200:
                data = downlink_response.json()
                download = data.get("stat", {}).get("value", 0)

            return {
                "upload": upload,
                "download": download,
                "total": upload + download
            }
        except Exception as e:
            print(f"❌ Ошибка получения статистики: {e}")
            return {"upload": 0, "download": 0, "total": 0}

    def get_all_stats(self) -> dict:
        """Получить общую статистику"""
        try:
            import requests
            response = requests.post(
                f"http://{self.api_url}/service/StatsService.QueryStats",
                json={"pattern": "user>>>", "reset": False},
                timeout=5
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"❌ Ошибка получения общей статистики: {e}")
        return {}

    def test_connection(self) -> bool:
        """Проверить подключение к API"""
        return self.connect()

    @staticmethod
    def format_bytes(bytes_num: int) -> str:
        """Форматирование байтов"""
        if bytes_num < 0:
            bytes_num = 0

        bytes_num = float(bytes_num)
        for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
            if bytes_num < 1024:
                return f"{bytes_num:.2f} {unit}"
            bytes_num /= 1024
        return f"{bytes_num:.2f} ПБ"

    def is_client_online(self, last_seen: Optional[datetime], timeout_minutes: int = 5) -> bool:
        """Проверка: клиент онлайн?"""
        if not last_seen:
            return False

        now = datetime.now(timezone.utc)
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)

        return now - last_seen < timedelta(minutes=timeout_minutes)


# Глобальный экземпляр
stats_service = XrayStatsService()