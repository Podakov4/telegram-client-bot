#!/usr/bin/env python3
"""Сервис для работы с 3x-ui / Xray"""

import json
import logging
import uuid
from typing import Optional

import requests

from config import (
    XUI_BASE_URL,
    XUI_WEB_BASE_PATH,
    XUI_USERNAME,
    XUI_PASSWORD,
    VLESS_DOMAIN,
    VLESS_PUBLIC_PORT,
    VLESS_PATH,
    VLESS_SECURITY,
    VLESS_SNI,
    XRAY_INBOUND_PORT,
)

logger = logging.getLogger(__name__)


class VLESSManager:
    def __init__(
        self,
        panel_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        self.panel_url = (panel_url or XUI_BASE_URL).rstrip("/")
        self.username = username or XUI_USERNAME
        self.password = password or XUI_PASSWORD
        self.session = requests.Session()

    def _join_url(self, path: str) -> str:
        base = self.panel_url.rstrip("/")
        prefix = f"/{XUI_WEB_BASE_PATH}" if XUI_WEB_BASE_PATH else ""
        return f"{base}{prefix}{path}"

    def login(self) -> bool:
        try:
            login_url = self._join_url("/login")

            response = self.session.post(
                login_url,
                json={
                    "username": self.username,
                    "password": self.password,
                },
                timeout=15,
            )

            logger.info("3x-ui login url=%s", login_url)
            logger.info("3x-ui login status=%s body=%s", response.status_code, response.text)

            if response.status_code != 200:
                logger.error("3x-ui login failed: HTTP %s", response.status_code)
                return False

            data = response.json()
            if not data.get("success"):
                logger.error("3x-ui login failed: %s", data.get("msg"))
                return False

            return True
        except Exception as e:
            logger.exception("Ошибка логина в 3x-ui: %s", e)
            return False

    def _api_url(self, path: str) -> str:
        return self._join_url(f"/panel/api/inbounds/{path}")

    def find_inbound_by_port(self, port: int) -> Optional[int]:
        try:
            response = self.session.get(self._api_url("list"), timeout=15)

            logger.info("inbounds list status=%s body=%s", response.status_code, response.text)

            if response.status_code != 200:
                logger.error("Не удалось получить список inbound: HTTP %s", response.status_code)
                return None

            data = response.json()
            if not data.get("success"):
                logger.error("Ошибка списка inbound: %s", data.get("msg"))
                return None

            for inbound in data.get("obj", []):
                if inbound.get("port") == port:
                    logger.info("Found inbound id=%s for port=%s", inbound.get("id"), port)
                    return inbound.get("id")

            logger.error("Inbound с портом %s не найден", port)
            return None
        except Exception as e:
            logger.exception("Ошибка поиска inbound: %s", e)
            return None

    def build_vless_link(self, client_uuid: str, remark: str) -> str:
        path = VLESS_PATH if VLESS_PATH.startswith("/") else f"/{VLESS_PATH}"
        remark = remark.replace(" ", "_")

        return (
            f"vless://{client_uuid}@{VLESS_DOMAIN}:{VLESS_PUBLIC_PORT}"
            f"?type=ws"
            f"&security={VLESS_SECURITY}"
            f"&encryption=none"
            f"&path=%2F{path.lstrip('/')}"
            f"&host={VLESS_DOMAIN}"
            f"&sni={VLESS_SNI}"
            f"#{remark}"
        )

    def add_client(
        self,
        telegram_id: str,
        full_name: str,
        xui_email: str,
        paid_until_ts_ms: int = 0,
        total_gb: int = 0,
    ) -> tuple[str, str, str] | None:
        if not self.login():
            return None

        inbound_id = self.find_inbound_by_port(XRAY_INBOUND_PORT)
        if not inbound_id:
            return None

        client_uuid = str(uuid.uuid4())

        settings = {
            "clients": [
                {
                    "id": client_uuid,
                    "email": xui_email,
                    "enable": True,
                    "expiryTime": paid_until_ts_ms,
                    "flow": "",
                    "limitIp": 0,
                    "totalGB": total_gb * 1024 * 1024 * 1024,
                    "tgId": telegram_id,
                    "subId": "",
                    "reset": 0,
                }
            ]
        }

        payload = {
            "id": inbound_id,
            "settings": json.dumps(settings),
        }

        try:
            add_url = self._api_url("addClient")

            logger.info("addClient url=%s", add_url)
            logger.info("addClient payload=%s", payload)

            response = self.session.post(
                add_url,
                json=payload,
                timeout=20,
            )

            logger.info("addClient status=%s body=%s", response.status_code, response.text)

            if response.status_code != 200:
                logger.error("Ошибка addClient: HTTP %s", response.status_code)
                return None

            data = response.json()
            if not data.get("success"):
                logger.error("Ошибка addClient: %s", data.get("msg"))
                return None

            subscription_link = self.build_vless_link(client_uuid, full_name or xui_email)
            return client_uuid, xui_email, subscription_link

        except Exception as e:
            logger.exception("Ошибка создания клиента в 3x-ui: %s", e)
            return None