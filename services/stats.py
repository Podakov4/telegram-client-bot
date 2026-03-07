# services/stats.py
import grpc
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict


# Proto-сообщения для Xray API (упрощённая версия)
class XrayStatsService:
    """gRPC сервис для получения статистики из Xray"""

    def __init__(self, api_url: str = "127.0.0.1:10085"):
        self.api_url = api_url
        self.channel = None
        self.stub = None

    def connect(self):
        """Подключение к gRPC серверу Xray"""
        try:
            self.channel = grpc.insecure_channel(self.api_url)
            grpc.channel_ready_future(self.channel).result(timeout=5)
            return True
        except Exception as e:
            print(f"❌ Ошибка подключения к Xray API: {e}")
            return False

    def close(self):
        """Закрытие соединения"""
        if self.channel:
            self.channel.close()

    def get_client_stats(self, email: str) -> dict:
        """Получить статистику по клиенту (email = UUID или client_X_name)"""
        if not self.connect():
            return {"upload": 0, "download": 0, "total": 0}

        try:
            # Формируем запрос к Xray API
            uplink = self._get_stat(f"user>>>{email}>>>traffic>>>uplink")
            downlink = self._get_stat(f"user>>>{email}>>>traffic>>>downlink")

            return {
                "upload": uplink,
                "download": downlink,
                "total": uplink + downlink
            }
        except Exception as e:
            print(f"❌ Ошибка получения статистики: {e}")
            return {"upload": 0, "download": 0, "total": 0}
        finally:
            self.close()

    def _get_stat(self, stat_name: str) -> int:
        """Получить конкретную статистику"""
        try:
            # Используем requests для простоты (Xray API поддерживает HTTP/JSON)
            import requests
            response = requests.post(
                f"http://{self.api_url}/service/StatsService.GetStats",
                json={"name": stat_name, "reset": False},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("stat", {}).get("value", 0)
        except:
            pass
        return 0

    def get_all_stats(self) -> dict:
        """Получить общую статистику"""
        if not self.connect():
            return {}

        try:
            import requests
            response = requests.post(
                f"http://{self.api_url}/service/StatsService.QueryStats",
                json={"pattern": "user>>>", "reset": False},
                timeout=5
            )
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return {}

    @staticmethod
    def format_bytes(bytes_num: int) -> str:
        """Форматирование байтов в человекочитаемый вид"""
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