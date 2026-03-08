# services/stats.py
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
import logging
from config import XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD, XUI_WEB_BASE_PATH

logger = logging.getLogger(__name__)


class XrayStatsService:
    """Сервис для получения статистики из 3x-ui через HTTP REST API"""

    def __init__(self, panel_url: str = None,
                 username: str = None,
                 password: str = None,
                 web_base_path: str = None):
        # Используем значения из config если не переданы
        self.panel_url = (panel_url or XUI_PANEL_URL).rstrip('/')
        self.username = username or XUI_USERNAME
        self.password = password or XUI_PASSWORD
        self.web_base_path = (web_base_path or XUI_WEB_BASE_PATH).strip('/')
        self.session_token = None

    def _get_api_url(self, endpoint: str) -> str:
        """Получить полный URL API"""
        if self.web_base_path:
            return f"{self.panel_url}/{self.web_base_path}/panel/api/inbounds/{endpoint}"
        return f"{self.panel_url}/panel/api/inbounds/{endpoint}"

    def _get_login_url(self) -> str:
        """Получить URL для входа"""
        if self.web_base_path:
            return f"{self.panel_url}/{self.web_base_path}/login"
        return f"{self.panel_url}/login"

    def login(self) -> bool:
        """Авторизация в панели 3x-ui"""
        try:
            login_url = self._get_login_url()

            logger.info(f"🔐 Попытка входа в {login_url}")

            response = requests.post(
                login_url,
                json={"username": self.username, "password": self.password},
                timeout=10
            )

            logger.info(f"📥 Ответ сервера: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                logger.info(f"📄 Данные ответа: {data}")

                if data.get("success"):
                    self.session_token = response.cookies.get("session")
                    if self.session_token:
                        logger.info("✅ Успешный вход в 3x-ui панель")
                        return True
                    else:
                        logger.error("❌ Нет session cookie в ответе")
                else:
                    logger.error(f"❌ Ошибка входа: {data.get('msg', 'Unknown error')}")
            else:
                logger.error(f"❌ HTTP ошибка: {response.status_code}")
                logger.error(f"📄 Ответ: {response.text}")

            return False

        except Exception as e:
            logger.error(f"❌ Ошибка подключения к панели: {e}")
            return False

    def get_client_stats(self, email: str) -> dict:
        """Получить статистику клиента по email"""
        try:
            # Сначала логинимся если нет токена
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

                    logger.info(f"✅ Статистика для {email}: ↑{upload} ↓{download}")

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

                    logger.info(f"✅ Найдено {len(clients)} клиентов")
                    return clients

            logger.error(f"❌ Ошибка получения списка клиентов: {response.status_code}")
            return []

        except Exception as e:
            logger.error(f"❌ Ошибка получения списка клиентов: {e}")
            return []

    def test_connection(self) -> bool:
        """Проверить подключение к панели"""
        logger.info("🔍 Проверка подключения к 3x-ui панели...")
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


# Глобальный экземпляр с конфигурацией из config.py
stats_service = XrayStatsService()