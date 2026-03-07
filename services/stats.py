# services/stats.py
from datetime import datetime, timedelta
from typing import Optional
import re
from datetime import datetime, timezone

class XrayStatsService:
    """Сервис для работы со статистикой"""

    def __init__(self):
        pass

    def get_client_stats(self, email: str) -> dict:
        """
        Получить статистику по клиенту.
        Пока заглушка - потом будет gRPC вызов к Xray API
        """
        # TODO: В будущем здесь будет gRPC запрос к Xray
        return {
            "upload": 0,
            "download": 0,
            "total": 0
        }

    def get_all_stats(self) -> dict:
        """Получить общую статистику (заглушка для gRPC)"""
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
        return datetime.now(timezone.utc) - last_seen < timedelta(minutes=timeout_minutes)

    @staticmethod
    def parse_xray_log_line(line: str) -> Optional[dict]:
        """
        Парсинг строки лога Xray для извлечения трафика
        Пример лога:
        2026/03/07 15:35:19 client_3_podakov_k traffic: uplink=1234 downlink=5678
        """
        # Ищем паттерн: email + traffic данные
        pattern = r'(\S+)\s+traffic:\s+uplink=(\d+)\s+downlink=(\d+)'
        match = re.search(pattern, line)

        if match:
            email = match.group(1)
            uplink = int(match.group(2))
            downlink = int(match.group(3))

            return {
                'email': email,
                'upload': uplink,
                'download': downlink
            }
        return None