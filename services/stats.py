# services/stats.py
import grpc
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict


class XrayStatsService:
    """Сервис для получения статистики из Xray API через gRPC"""

    def __init__(self, api_url: str = "127.0.0.1:10085"):
        self.api_url = api_url
        self.channel = None

    def connect(self) -> bool:
        """Подключение к gRPC серверу"""
        try:
            self.channel = grpc.insecure_channel(self.api_url)
            grpc.channel_ready_future(self.channel).result(timeout=5)
            return True
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            return False

    def close(self):
        """Закрытие соединения"""
        if self.channel:
            self.channel.close()
            self.channel = None

    def get_client_stats(self, email: str) -> dict:
        """Получить статистику по клиенту через gRPC"""
        if not self.connect():
            return {"upload": 0, "download": 0, "total": 0}

        try:
            # Импортируем готовые proto классы из xray-rpc
            from xray.api.stats_service_pb2 import GetStatsRequest
            from xray.api.stats_service_pb2_grpc import StatsServiceStub

            # Создаём stub
            stub = StatsServiceStub(self.channel)

            # Запрос uplink
            uplink_req = GetStatsRequest(
                name=f"user>>>{email}>>>traffic>>>uplink",
                reset=False
            )
            uplink_resp = stub.GetStats(uplink_req)
            upload = uplink_resp.stat.value if uplink_resp.stat else 0

            # Запрос downlink
            downlink_req = GetStatsRequest(
                name=f"user>>>{email}>>>traffic>>>downlink",
                reset=False
            )
            downlink_resp = stub.GetStats(downlink_req)
            download = downlink_resp.stat.value if downlink_resp.stat else 0

            return {
                "upload": upload,
                "download": download,
                "total": upload + download
            }
        except ImportError:
            print("⚠️ xray-rpc не установлен, используем fallback")
            return {"upload": 0, "download": 0, "total": 0}
        except Exception as e:
            print(f"❌ Ошибка получения статистики: {e}")
            return {"upload": 0, "download": 0, "total": 0}
        finally:
            self.close()

    def get_all_stats(self) -> dict:
        """Получить общую статистику через gRPC"""
        if not self.connect():
            return {}

        try:
            from xray.api.stats_service_pb2 import QueryStatsRequest
            from xray.api.stats_service_pb2_grpc import StatsServiceStub

            stub = StatsServiceStub(self.channel)

            req = QueryStatsRequest(pattern="user>>>", reset=False)
            resp = stub.QueryStats(req)

            return {
                "stat": [
                    {"name": stat.name, "value": stat.value}
                    for stat in resp.stat
                ]
            }
        except ImportError:
            print("⚠️ xray-rpc не установлен")
            return {}
        except Exception as e:
            print(f"❌ Ошибка получения общей статистики: {e}")
            return {}
        finally:
            self.close()

    def test_connection(self) -> bool:
        """Проверить подключение"""
        return self.connect()

    @staticmethod
    def format_bytes(bytes_num: int) -> str:
        """Форматирование байтов"""
        if bytes_num < 0:
            bytes_num = 0
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