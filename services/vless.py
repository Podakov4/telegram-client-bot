# services/vless.py
import uuid
import json
import subprocess
from typing import Optional, Tuple
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
        """
        Добавление клиента в Xray конфиг
        Возвращает: (uuid, vless_link)
        """
        # Генерация UUID
        client_uuid = self.generate_uuid()

        # Email для Xray
        client_email = email or f"client_{client_id}"
        # Ограничиваем длину email (Xray требует < 64 символов)
        client_email = client_email[:60].replace(" ", "_").lower()

        # Чтение текущего конфига
        try:
            with open(self.XRAY_CONFIG_PATH, 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            # Создаём новый конфиг если нет
            config = {
                "inbounds": [
                    {
                        "listen": "127.0.0.1",
                        "port": 10443,
                        "protocol": "vless",
                        "settings": {
                            "clients": [],
                            "decryption": "none"
                        },
                        "streamSettings": {
                            "network": "ws",
                            "wsSettings": {
                                "path": "/vless"
                            }
                        },
                        "sniffing": {
                            "enabled": True,
                            "destOverride": ["http", "tls"]
                        }
                    }
                ],
                "outbounds": [
                    {
                        "protocol": "freedom",
                        "tag": "direct"
                    }
                ],
                "log": {
                    "loglevel": "warning"
                }
            }

        # Проверка что есть inbound
        if not config.get("inbounds"):
            config["inbounds"] = []

        # Находим VLESS inbound или создаём новый
        vless_inbound = None
        for inbound in config["inbounds"]:
            if inbound.get("protocol") == "vless":
                vless_inbound = inbound
                break

        if not vless_inbound:
            # Создаём новый VLESS inbound
            vless_inbound = {
                "listen": "127.0.0.1",
                "port": 10443,
                "protocol": "vless",
                "settings": {
                    "clients": [],
                    "decryption": "none"
                },
                "streamSettings": {
                    "network": "ws",
                    "wsSettings": {
                        "path": "/vless"
                    }
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls"]
                }
            }
            config["inbounds"].append(vless_inbound)

        # Проверка что есть clients
        if not vless_inbound.get("settings", {}).get("clients"):
            vless_inbound["settings"]["clients"] = []

        # Проверка что клиент ещё не добавлен
        for client in vless_inbound["settings"]["clients"]:
            if client.get("email") == client_email:
                # Клиент уже есть, используем его UUID
                client_uuid = client.get("id")
                break

        # Добавление нового клиента
        new_client = {
            "id": client_uuid,
            "email": client_email,
            "level": 0,
            "flow": ""
        }

        # Проверяем что клиент с таким email ещё не существует
        existing_emails = [c.get("email") for c in vless_inbound["settings"]["clients"]]
        if client_email not in existing_emails:
            vless_inbound["settings"]["clients"].append(new_client)

        # Сохранение конфига
        with open(self.XRAY_CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)

        # Перезапуск Xray
        try:
            subprocess.run(
                ["sudo", "systemctl", "restart", "xray"],
                check=True,
                capture_output=True
            )
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Ошибка перезапуска Xray: {e}")
            # Пробуем reload вместо restart
            subprocess.run(
                ["sudo", "systemctl", "reload", "xray"],
                capture_output=True
            )

        # Генерация ссылки
        remark = f"Client_{client_id}_{full_name[:15]}" if full_name else f"Client_{client_id}"
        vless_link = self.generate_vless_link(
            user_id=str(client_id),
            uuid=client_uuid,
            remark=remark
        )

        return client_uuid, vless_link

    def remove_client_from_xray(self, email: str) -> bool:
        """Удаление клиента из Xray конфига"""
        try:
            with open(self.XRAY_CONFIG_PATH, 'r') as f:
                config = json.load(f)

            for inbound in config.get("inbounds", []):
                if inbound.get("protocol") == "vless":
                    clients = inbound.get("settings", {}).get("clients", [])
                    inbound["settings"]["clients"] = [
                        c for c in clients if c.get("email") != email
                    ]
                    break

            with open(self.XRAY_CONFIG_PATH, 'w') as f:
                json.dump(config, f, indent=2)

            subprocess.run(
                ["sudo", "systemctl", "restart", "xray"],
                check=True,
                capture_output=True
            )

            return True
        except Exception as e:
            print(f"❌ Ошибка удаления клиента: {e}")
            return False