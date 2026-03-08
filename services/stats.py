import requests
import json
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
        self.panel_url = (panel_url or XUI_PANEL_URL).rstrip('/')
        self.username = username or XUI_USERNAME
        self.password = password or XUI_PASSWORD
        self.web_base_path = (web_base_path or XUI_WEB_BASE_PATH).strip('/')
        self.session_token = None

    def _get_api_url(self, endpoint: str) -> str:
        base = f"{self.panel_url}/panel/api/inbounds/"
        if self.web_base_path:
            return f"{self.panel_url}/{self.web_base_path}{base}{endpoint}"
        return f"{self.panel_url}{base}{endpoint}"

    def _get_login_url(self) -> str:
        base = f"{self.panel_url}/login"
        if self.web_base_path:
            return f"{self.panel_url}/{self.web_base_path}/login"
        return base

    def login(self) -> bool:
        try:
            login_url = self._get_login_url()

            response = requests.post(
                login_url,
                json={"username": self.username, "password": self.password},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    self.session_token = response.cookies.get("3x-ui")
                    if self.session_token:
                        logger.info("✅ Успешный вход в 3x-ui панель")
                        return True
                else:
                    logger.error(f"❌ Ошибка входа: {data.get('msg', 'Unknown error')}")
            else:
                logger.error(f"❌ HTTP ошибка: {response.status_code}")

            return False

        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return False

    def get_client_stats(self, email: str) -> dict:
        try:
            if not self.session_token:
                if not self.login():
                    return {"upload": 0, "download": 0, "total": 0}

            api_url = self._get_api_url(f"getClientTraffics/{email}")

            response = requests.get(api_url, cookies={"3x-ui": self.session_token}, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    obj = data.get("obj", {})
                    return {
                        "upload": obj.get("up", 0),
                        "download": obj.get("down", 0),
                        "total": obj.get("up", 0) + obj.get("down", 0)
                    }

            return {"upload": 0, "download": 0, "total": 0}

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики {email}: {e}")
            return {"upload": 0, "download": 0, "total": 0}

    def get_all_clients(self) -> list:
        try:
            if not self.session_token:
                if not self.login():
                    return []

            api_url = self._get_api_url("list")

            response = requests.get(api_url, cookies={"3x-ui": self.session_token}, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and data.get("success"):
                    clients = []
                    for inbound in data.get("obj", []):
                        settings_raw = inbound.get("settings", "{}")

                        if isinstance(settings_raw, str):
                            try:
                                settings = json.loads(settings_raw)
                            except json.JSONDecodeError:
                                continue
                        else:
                            settings = settings_raw

                        for client in settings.get("clients", []):
                            email = client.get("email")
                            if email:
                                clients.append(email)

                    logger.info(f"✅ Найдено {len(clients)} клиентов")
                    return clients

            return []

        except Exception as e:
            logger.error(f"❌ Ошибка списка клиентов: {e}")
            return []

    def test_connection(self) -> bool:
        return self.login()

    @staticmethod
    def format_bytes(bytes_num: int) -> str:
        if bytes_num < 0:
            bytes_num = 0
        bytes_num = float(bytes_num)
        for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
            if bytes_num < 1024:
                return f"{bytes_num:.2f} {unit}"
            bytes_num /= 1024
        return f"{bytes_num:.2f} ПБ"


# Глобальный экземпляр
stats_service = XrayStatsService()