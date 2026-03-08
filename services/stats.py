# services/stats.py
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


class XrayStatsService:
    """Сервис для получения статистики из 3x-ui через HTTP REST API"""

    def __init__(self, panel_url: str = "http://127.0.0.1:2053",
                 username: str = "admin",
                 password: str = "admin",
                 web_base_path: str = ""):
        self.panel_url = panel_url.rstrip('/')
        self.web_base_path = web_base_path.strip('/')
        self.username = username
        self.password = password
        self.session_token = None

    def _get_api_url(self, endpoint: str) -> str:
        """Получить полный URL API"""
        if self.web_base_path:
            return f"{self.panel_url}/{self.web_base_path}/panel/api/inbounds/{endpoint}"
        return f"{self.panel_url}/panel/api/inbounds/{endpoint}"

    def login(self) -> bool:
        """Авторизация в панели 3x-ui"""
        try:
            login_url = f"{self.panel_url}/{self.web_base_path}/login" if self.web_base_path else f"{self.panel_url}/login"

            response = requests.post(
                login_url,
                json={"username": self.username, "password": self.password},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    self.session_token = response.cookies.get("session")
                    logger.info("✅ Успешный вход в 3x-ui панель")
                    return True

            logger.error(f"❌ Ошибка входа: {response.status_code}")
            return False

        except Exception as e:
            logger.error(f"❌ Ошибка подключения к панели: {e}")
            return False

    def get_client_stats(self, email: str) -> dict:
        """Получить статистику клиента по email"""
        try:
            # Сначала логинимся
            if not self.session_token:
                if not self.login():
                    return {"upload": 0, "download": 0, "total": 0}

            # Получаем статистику клиента
            api_url = self._get_api_url(f"getClientTraffics/{email}")

            response = requests.get(
                api_url,
                cookies={"session": self.session_token} if self.session_token else None,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    obj = data.get("obj", {})
                    upload = obj.get("up", 0)
                    download = obj.get("down", 0)

                    return {
                        "upload": upload,
                        "download": download,
                        "total": upload + download
                    }

            logger.warning(f"⚠️ Не удалось получить статистику для {email}: {response.status_code}")
            return {"upload": 0, "download": 0, "total": 0}

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики клиента {email}: {e}")
            return {"upload": 0, "download": 0, "total": 0}

    def get_all_clients(self) -> list:
        """Получить список всех клиентов"""
        try:
            if not self.session_token:
                if not self.login():
                    return []

            api_url = self._get_api_url("list")

            response = requests.get(
                api_url,
                cookies={"session": self.session_token} if self.session_token else None,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    clients = []
                    for inbound in data.get("obj", []):
                        settings = inbound.get("settings", {})
                        for client in settings.get("clients", []):
                            email = client.get("email")
                            if email:
                                clients.append(email)
                    return clients

            logger.error(f"❌ Ошибка получения списка клиентов: {response.status_code}")
            return []

        except Exception as e:
            logger.error(f"❌ Ошибка получения списка клиентов: {e}")
            return []

    def test_connection(self) -> bool:
        """Проверить подключение к панели"""
        return self.login()

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


# Глобальный экземпляр (будет переопределён в update_stats.py)
stats_service = XrayStatsService()