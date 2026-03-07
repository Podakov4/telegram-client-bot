# services/vless.py
import uuid
import json
import subprocess
import os
from typing import Tuple
from urllib.parse import quote


class VLESSManager:
    """Управление VLESS клиентами"""

    XRAY_CONFIG_PATH = "/usr/local/etc/xray/config.json"

    def __init__(self, server_ip: str, port: int = 443,
                 path: str = "/vless", host: str = ""):
        self.server_ip = server_ip
        self.port = port
        self.path = path
        self.host = host or server_ip

    def generate_uuid(self) -> str:
        """Генерация UUID для клиента"""
        return str(uuid.uuid4())

    def generate_vless_link(self, user_id: str, uuid: str,
                            remark: str = "Client") -> str:
        """Генерация vless:// ссылки"""
        params = {
            "security": "tls",
            "sni": self.host,
            "fp": "chrome",
            "alpn": "h2,http/1.1",
            "type": "ws",
            "path": self.path,
            "host": self.host
        }

        query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
        link = f"vless://{uuid}@{self.server_ip}:{self.port}?{query}#{quote(remark)}"

        return link

    def add_client_to_xray(self, client_id: int, full_name: str,
                           email: str = None) -> Tuple[str, str]:
        """Добавление клиента в Xray конфиг"""
        client_uuid = self.generate_uuid()
        client_email = (email or f"client_{client_id}")[:60].replace(" ", "_").lower()

        # Проверка существует ли конфиг Xray
        if not os.path.exists(self.XRAY_CONFIG_PATH):
            print(f"⚠️ Xray конфиг не найден: {self.XRAY_CONFIG_PATH}")
            print(f"⚠️ Работа в режиме заглушки")
            remark = f"Client_{client_id}_{full_name[:15]}" if full_name else f"Client_{client_id}"
            return client_uuid, self.generate_vless_link(str(client_id), client_uuid, remark)

        try:
            with open(self.XRAY_CONFIG_PATH, 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            config = {
                "inbounds": [{
                    "listen": "127.0.0.1",
                    "port": 10443,
                    "protocol": "vless",
                    "settings": {"clients": [], "decryption": "none"},
                    "streamSettings": {
                        "network": "ws",
                        "wsSettings": {"path": "/vless"}
                    }
                }],
                "outbounds": [{"protocol": "freedom"}]
            }

        if not config.get("inbounds"):
            config["inbounds"] = []

        vless_inbound = None
        for inbound in config["inbounds"]:
            if inbound.get("protocol") == "vless":
                vless_inbound = inbound
                break

        if not vless_inbound:
            vless_inbound = {
                "listen": "127.0.0.1",
                "port": 10443,
                "protocol": "vless",
                "settings": {"clients": [], "decryption": "none"},
                "streamSettings": {
                    "network": "ws",
                    "wsSettings": {"path": "/vless"}
                }
            }
            config["inbounds"].append(vless_inbound)

        if not vless_inbound.get("settings", {}).get("clients"):
            vless_inbound["settings"]["clients"] = []

        for client in vless_inbound["settings"]["clients"]:
            if client.get("email") == client_email:
                client_uuid = client.get("id")
                break

        new_client = {
            "id": client_uuid,
            "email": client_email,
            "level": 0,
            "flow": ""
        }

        existing_emails = [c.get("email") for c in vless_inbound["settings"]["clients"]]
        if client_email not in existing_emails:
            vless_inbound["settings"]["clients"].append(new_client)

        with open(self.XRAY_CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)

        # 🔥 Перезапуск Xray: без sudo если root, с абсолютным путём
        try:
            systemctl_cmd = "/usr/bin/systemctl"
            if os.geteuid() == 0:
                # Запущен от root - sudo не нужен
                subprocess.run(
                    [systemctl_cmd, "restart", "xray"],
                    check=True,
                    capture_output=True
                )
            else:
                # Не от root - нужен sudo
                subprocess.run(
                    ["sudo", systemctl_cmd, "restart", "xray"],
                    check=True,
                    capture_output=True
                )
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Ошибка перезапуска Xray: {e}")
        except FileNotFoundError:
            print(f"⚠️ systemctl не найден, пропускаем перезапуск")

        remark = f"Client_{client_id}_{full_name[:15]}" if full_name else f"Client_{client_id}"
        vless_link = self.generate_vless_link(
            user_id=str(client_id),
            uuid=client_uuid,
            remark=remark
        )

        return client_uuid, vless_link