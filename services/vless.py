#!/usr/bin/env python3
"""Сервис для генерации VLESS ссылок и управления клиентами Xray"""
import uuid
import requests
import json
import logging
from typing import Optional, Tuple
from datetime import datetime, timedelta, timezone
from config import XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD, XUI_WEB_BASE_PATH, VLESS_PORT, VLESS_PATH

logger = logging.getLogger(__name__)


class VLESSManager:
    """Менеджер клиентов VLESS через REST API 3x-ui"""

    def __init__(self, panel_url: str = None,
                 username: str = None,
                 password: str = None,
                 web_base_path: str = None):
        self.panel_url = (panel_url or XUI_PANEL_URL).rstrip('/')
        self.username = username or XUI_USERNAME
        self.password = password or XUI_PASSWORD
        self.web_base_path = (web_base_path or XUI_WEB_BASE_PATH).strip('/') if web_base_path else ""
        self.session_token = None

    def _get_api_base(self) -> str:
        """Получить базовый путь API"""
        base = "panel/api/inbounds/"
        if self.web_base_path:
            return f"{self.panel_url}/{self.web_base_path}/{base}"
        return f"{self.panel_url}/{base}"

    def login(self) -> bool:
        """Авторизация в 3x-ui"""
        try:
            if self.web_base_path:
                login_url = f"{self.panel_url}/{self.web_base_path}/login"
            else:
                login_url = f"{self.panel_url}/login"

            response = requests.post(
                login_url,
                json={"username": self.username, "password": self.password},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    self.session_token = response.cookies.get("3x-ui")
                    logger.info("✅ Авторизация успешна!")
                    return True

            logger.error(f"❌ Ошибка входа: {response.status_code}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return False

    def find_inbound_by_port(self, port: int) -> Optional[int]:
        """Найти Inbound по порту"""
        try:
            url = self._get_api_base() + "list"
            resp = requests.get(url, cookies={"3x-ui": self.session_token}, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    # Сначала ищем по порту
                    for inbound in data.get("obj", []):
                        if inbound.get("port") == port:
                            logger.info(f"✅ Найден Inbound с портом {port}: ID={inbound['id']}")
                            return inbound.get("id")

                    # Если не нашли, используем первый vless
                    for inbound in data.get("obj", []):
                        if inbound.get("protocol", "").lower() == "vless":
                            logger.warning(f"⚠️ Inbound с портом {port} не найден, используем: ID={inbound.get('id')}")
                            return inbound.get("id")

            logger.error("❌ Inbound не найден!")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка поиска Inbound: {e}")
            return None

    def add_client_to_xray(self, client_id: int, full_name: str, email: str,
                           total_gb: int = 0, expiry_time: int = 0) -> Tuple[str, str]:
        """
        Добавить клиента в Xray и вернуть UUID и ссылку

        Returns:
            Tuple[uuid, vless_link]
        """
        try:
            if not self.session_token:
                if not self.login():
                    raise Exception("Не удалось авторизоваться!")

            # Находим inbound с нужным портом
            inbound_id = self.find_inbound_by_port(VLESS_PORT)
            if not inbound_id:
                raise Exception("Inbound не найден!")

            # Генерируем UUID
            client_uuid = str(uuid.uuid4())

            # Добавляем клиента в inbound
            payload = {
                "id": inbound_id,
                "settings": json.dumps({
                    "clients": [{
                        "email": email,
                        "enabled": True,
                        "expiryTime": expiry_time,
                        "flow": "",
                        "id": client_uuid,
                        "ip": "",
                        "limitIp": 0,
                        "limits": {},
                        "method": "noencryption",
                        "overallLimit": total_gb * 1024 * 1024 * 1024,
                        "reset": 0,
                        "tgId": str(client_id),
                        "totalGB": 0,
                        "uplinkSpeed": 0,
                        "downlinkSpeed": 0
                    }]
                })
            }

            # Отправляем запрос
            url = self._get_api_base() + "addClient"
            response = requests.post(
                url,
                json=payload,
                cookies={"3x-ui": self.session_token},
                timeout=30
            )

            result = response.json()
            if result.get("success"):
                logger.info(f"✅ Клиент {email} успешно добавлен!")
            else:
                logger.error(f"❌ Ошибка добавления клиента: {result.get('msg')}")
                return "", ""

            # Генерируем VLESS ссылку ПО ОБРАЗЦУ ИЗ ПАНЕЛИ
            domain = "freeth.ru"
            path = VLESS_PATH.lstrip("/")

            # Параметры согласно ВАШЕМУ образцу ссылки из панели:
            params = [
                f"type=ws",
                f"encryption=none",
                f"path=%2F{path}",  # URL encoded
                f"host={domain}",
                f"sni={domain}",  # ⚠️ ДОБАВИЛ это важно для TLS
                "security=none"  # Как в вашем образце из панели
            ]

            query_string = "&".join(params)
            # Включаем порт из конфига - правильный!
            vless_link = f"vless://{client_uuid}@{domain}:{VLESS_PORT}?{query_string}#{full_name.replace(' ', '_')}"

            logger.info(f"🔗 Сгенерирована ссылка: {vless_link}")
            return client_uuid, vless_link

        except Exception as e:
            logger.error(f"❌ Ошибка добавления клиента: {e}")
            import traceback
            traceback.print_exc()
            return "", ""

    def update_client_traffic(self, email: str, upload: int = 0, download: int = 0):
        """Обновить трафик клиента"""
        # TODO: Реализовать обновление трафика через API
        pass

    def get_client_stats(self, email: str) -> dict:
        """Получить статистику клиента"""
        # TODO: Реализовать получение статистики
        return {"upload": 0, "download": 0, "total": 0}


# Глобальный экземпляр
vless_manager_default = VLESSManager()