# services/vless.py
import uuid
from typing import Optional
from urllib.parse import quote


class VLESSManager:
    """Управление VLESS клиентами"""

    def __init__(self, server_ip: str, port: int = 443,
                 path: str = "/vless", host: str = ""):
        self.server_ip = server_ip
        self.port = port  # 🔥 Теперь 443
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

    def add_client_to_xray(self, db_session, client_id: int,
                           full_name: str) -> tuple[str, str]:
        """Добавление клиента в Xray конфиг"""
        client_uuid = self.generate_uuid()
        remark = f"Client_{client_id}_{full_name[:10]}"
        vless_link = self.generate_vless_link(
            user_id=str(client_id),
            uuid=client_uuid,
            remark=remark
        )

        return client_uuid, vless_link