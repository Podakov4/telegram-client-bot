#!/usr/bin/env python3
"""Сервис для работы с 3x-ui / Xray"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import requests

from config import (
    VLESS_DOMAIN,
    VLESS_PATH,
    VLESS_PUBLIC_PORT,
    VLESS_SECURITY,
    VLESS_SNI,
    XRAY_INBOUND_PORT,
    XUI_BASE_URL,
    XUI_PASSWORD,
    XUI_USERNAME,
    XUI_WEB_BASE_PATH,
)

logger = logging.getLogger(__name__)

SERVER_DISPLAY_NAME = "🇳🇱 Amsterdam"


@dataclass(slots=True)
class NodeConfig:
    code: str
    name: str
    display_name: str
    panel_url: str
    username: str
    password: str
    web_base_path: str = ""
    inbound_port: int = XRAY_INBOUND_PORT
    vless_domain: str = VLESS_DOMAIN
    vless_public_port: int = VLESS_PUBLIC_PORT
    vless_path: str = VLESS_PATH
    vless_security: str = VLESS_SECURITY
    vless_sni: str = VLESS_SNI


DEFAULT_NODE_CONFIG = NodeConfig(
    code="nl",
    name="Netherlands",
    display_name=SERVER_DISPLAY_NAME,
    panel_url=XUI_BASE_URL,
    username=XUI_USERNAME,
    password=XUI_PASSWORD,
    web_base_path=XUI_WEB_BASE_PATH,
    inbound_port=XRAY_INBOUND_PORT,
    vless_domain=VLESS_DOMAIN,
    vless_public_port=VLESS_PUBLIC_PORT,
    vless_path=VLESS_PATH,
    vless_security=VLESS_SECURITY,
    vless_sni=VLESS_SNI,
)


class VLESSManager:
    def __init__(
        self,
        node_config: NodeConfig | None = None,
        panel_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        self.node_config = node_config or DEFAULT_NODE_CONFIG
        self.panel_url = (panel_url or self.node_config.panel_url).rstrip("/")
        self.username = username or self.node_config.username
        self.password = password or self.node_config.password
        self.web_base_path = (self.node_config.web_base_path or "").strip("/")
        self.inbound_port = int(self.node_config.inbound_port)
        self.session = requests.Session()

    def _join_url(self, path: str) -> str:
        base = self.panel_url.rstrip("/")
        prefix = f"/{self.web_base_path}" if self.web_base_path else ""
        return f"{base}{prefix}{path}"

    def _api_url(self, path: str) -> str:
        return self._join_url(f"/panel/api/inbounds/{path}")

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
            logger.info("3x-ui login status=%s", response.status_code)

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

    def _list_inbounds(self) -> list[dict]:
        response = self.session.get(self._api_url("list"), timeout=15)
        logger.info("inbounds list status=%s", response.status_code)

        if response.status_code != 200:
            logger.error("Не удалось получить список inbound: HTTP %s", response.status_code)
            return []

        data = response.json()
        if not data.get("success"):
            logger.error("Ошибка списка inbound: %s", data.get("msg"))
            return []

        return data.get("obj", [])

    def find_inbound_by_port(self, port: int) -> Optional[int]:
        """
        В твоей версии x-ui API inbound list может возвращать port=0 и protocol=""
        даже для рабочего inbound. Поэтому:
        1. сначала пробуем обычный поиск по port
        2. если не нашли, берём первый inbound, у которого есть clients в settings
        """
        try:
            inbounds = self._list_inbounds()

            for inbound in inbounds:
                inbound_port = inbound.get("port")
                if str(inbound_port) == str(port):
                    logger.info(
                        "Found inbound id=%s for port=%s (raw=%s)",
                        inbound.get("id"),
                        port,
                        inbound_port,
                    )
                    return inbound.get("id")

            for inbound in inbounds:
                settings_raw = inbound.get("settings") or "{}"
                try:
                    settings = json.loads(settings_raw) if isinstance(settings_raw, str) else settings_raw
                except Exception:
                    settings = {}

                clients = settings.get("clients", [])
                if clients:
                    logger.warning(
                        "Inbound by port=%s not found, using fallback inbound id=%s with %s clients",
                        port,
                        inbound.get("id"),
                        len(clients),
                    )
                    return inbound.get("id")

            logger.error("Inbound с портом %s не найден", port)
            return None
        except Exception as e:
            logger.exception("Ошибка поиска inbound: %s", e)
            return None

    def get_inbound(self, inbound_id: int) -> Optional[dict]:
        try:
            response = self.session.get(self._api_url(f"get/{inbound_id}"), timeout=15)
            logger.info("get inbound status=%s", response.status_code)

            if response.status_code != 200:
                logger.error("Не удалось получить inbound: HTTP %s", response.status_code)
                return None

            data = response.json()
            if not data.get("success"):
                logger.error("Ошибка получения inbound: %s", data.get("msg"))
                return None

            return data.get("obj")
        except Exception as e:
            logger.exception("Ошибка получения inbound: %s", e)
            return None

    def _load_clients_from_inbound(self, inbound: dict) -> list[dict]:
        settings_raw = inbound.get("settings") or "{}"
        if isinstance(settings_raw, str):
            settings = json.loads(settings_raw)
        else:
            settings = settings_raw
        return settings.get("clients", [])

    def _save_clients_to_inbound(self, inbound_id: int, clients: list[dict]) -> bool:
        inbound = self.get_inbound(inbound_id)
        if not inbound:
            logger.error("Не удалось получить полный inbound для сохранения clients")
            return False

        settings_raw = inbound.get("settings") or "{}"
        if isinstance(settings_raw, str):
            settings = json.loads(settings_raw)
        else:
            settings = settings_raw

        settings["clients"] = clients

        payload = {
            "id": inbound_id,
            "up": inbound.get("up", 0),
            "down": inbound.get("down", 0),
            "total": inbound.get("total", 0),
            "remark": inbound.get("remark", ""),
            "enable": inbound.get("enable", True),
            "expiryTime": inbound.get("expiryTime", 0),
            "listen": inbound.get("listen", ""),
            "port": inbound.get("port"),
            "protocol": inbound.get("protocol"),
            "settings": json.dumps(settings, ensure_ascii=False),
            "streamSettings": inbound.get("streamSettings", "{}"),
            "sniffing": inbound.get("sniffing", "{}"),
            "allocate": inbound.get("allocate", "{}"),
        }

        try:
            update_url = self._api_url(f"update/{inbound_id}")
            response = self.session.post(update_url, json=payload, timeout=20)

            logger.info("update inbound status=%s", response.status_code)

            if response.status_code != 200:
                logger.error("Ошибка update inbound: HTTP %s", response.status_code)
                logger.error("Response text: %s", response.text)
                return False

            data = response.json()
            if not data.get("success"):
                logger.error("Ошибка update inbound: %s", data.get("msg"))
                return False

            return True
        except Exception as e:
            logger.exception("Ошибка сохранения inbound: %s", e)
            return False

    def find_client(
        self,
        *,
        email: str | None = None,
        client_uuid: str | None = None,
    ) -> tuple[int, dict, list[dict]] | None:
        if not self.login():
            return None

        inbound_id = self.find_inbound_by_port(self.inbound_port)
        if not inbound_id:
            return None

        inbound = self.get_inbound(inbound_id)
        if not inbound:
            return None

        clients = self._load_clients_from_inbound(inbound)

        for client in clients:
            if email and client.get("email") == email:
                return inbound_id, client, clients
            if client_uuid and client.get("id") == client_uuid:
                return inbound_id, client, clients

        return None

    def client_exists(
        self,
        *,
        email: str | None = None,
        client_uuid: str | None = None,
    ) -> bool:
        return self.find_client(email=email, client_uuid=client_uuid) is not None

    def build_vless_link(
        self,
        client_uuid: str,
        title: str | None = None,
    ) -> str:
        path = self.node_config.vless_path if self.node_config.vless_path.startswith("/") else f"/{self.node_config.vless_path}"
        title_encoded = quote(title or self.node_config.display_name, safe="")

        return (
            f"vless://{client_uuid}@{self.node_config.vless_domain}:{self.node_config.vless_public_port}"
            f"?type=ws"
            f"&security={self.node_config.vless_security}"
            f"&encryption=none"
            f"&path=%2F{path.lstrip('/')}"
            f"&host={self.node_config.vless_domain}"
            f"&sni={self.node_config.vless_sni}"
            f"#{title_encoded}"
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

        inbound_id = self.find_inbound_by_port(self.inbound_port)
        if not inbound_id:
            return None

        existing = self.find_client(email=xui_email)
        if existing:
            _, client_obj, _ = existing
            logger.info("Client already exists in 3x-ui email=%s", xui_email)

            self.update_client(
                email=xui_email,
                enable=True,
                expiry_time_ms=paid_until_ts_ms,
                total_gb=total_gb,
            )

            link = self.build_vless_link(client_obj["id"])
            return client_obj["id"], xui_email, link

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
            response = self.session.post(add_url, json=payload, timeout=20)

            logger.info("addClient status=%s", response.status_code)

            if response.status_code != 200:
                logger.error("Ошибка addClient: HTTP %s", response.status_code)
                logger.error("Response text: %s", response.text)
                return None

            data = response.json()
            if not data.get("success"):
                logger.error("Ошибка addClient: %s", data.get("msg"))
                return None

            subscription_link = self.build_vless_link(client_uuid)
            return client_uuid, xui_email, subscription_link

        except Exception as e:
            logger.exception("Ошибка создания клиента в 3x-ui: %s", e)
            return None

    def update_client(
        self,
        *,
        email: str | None = None,
        client_uuid: str | None = None,
        enable: bool | None = None,
        expiry_time_ms: int | None = None,
        total_gb: int | None = None,
    ) -> bool:
        found = self.find_client(email=email, client_uuid=client_uuid)
        if not found:
            logger.error("Клиент в 3x-ui не найден email=%s uuid=%s", email, client_uuid)
            return False

        inbound_id, _, clients = found
        updated = False

        for item in clients:
            is_match = False
            if email and item.get("email") == email:
                is_match = True
            if client_uuid and item.get("id") == client_uuid:
                is_match = True

            if is_match:
                if enable is not None:
                    item["enable"] = enable
                if expiry_time_ms is not None:
                    item["expiryTime"] = expiry_time_ms
                if total_gb is not None:
                    item["totalGB"] = total_gb * 1024 * 1024 * 1024
                updated = True
                break

        if not updated:
            logger.error("Совпадающий клиент для update не найден email=%s uuid=%s", email, client_uuid)
            return False

        return self._save_clients_to_inbound(inbound_id, clients)

    def disable_client(
        self,
        *,
        email: str | None = None,
        client_uuid: str | None = None,
    ) -> bool:
        return self.update_client(
            email=email,
            client_uuid=client_uuid,
            enable=False,
        )

    def enable_client(
        self,
        *,
        email: str | None = None,
        client_uuid: str | None = None,
        expiry_time_ms: int | None = None,
        total_gb: int | None = None,
    ) -> bool:
        return self.update_client(
            email=email,
            client_uuid=client_uuid,
            enable=True,
            expiry_time_ms=expiry_time_ms,
            total_gb=total_gb,
        )

    def get_client_link(
        self,
        *,
        email: str | None = None,
        client_uuid: str | None = None,
    ) -> Optional[str]:
        found = self.find_client(email=email, client_uuid=client_uuid)
        if not found:
            return None

        _, client_obj, _ = found
        uuid_value = client_obj.get("id")
        if not uuid_value:
            return None

        return self.build_vless_link(uuid_value)

    def ensure_client_active(
        self,
        *,
        email: str | None = None,
        client_uuid: str | None = None,
        expiry_time_ms: int | None = None,
        total_gb: int | None = None,
    ) -> bool:
        return self.enable_client(
            email=email,
            client_uuid=client_uuid,
            expiry_time_ms=expiry_time_ms,
            total_gb=total_gb,
        )
