from __future__ import annotations

from datetime import datetime
import logging
import re
import secrets
from typing import Optional
from urllib.parse import quote as url_quote

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from config import APP_BASE_URL
from database.db import AsyncSessionLocal
from database.models import Client, ClientVpnAccess, VpnNode
from services.vless import DEFAULT_NODE_CONFIG, NodeConfig, VLESSManager

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = ["android", "ios", "windows", "macos"]


class ClientAccessError(Exception):
    pass


def make_xui_email(client: Client) -> str:
    raw_name = client.full_name or (client.email.split("@")[0] if client.email else f"user_{client.id}")
    base_name = raw_name.lower().strip()
    base_name = base_name.replace(" ", "_")
    base_name = re.sub(r"[^a-zA-Z0-9_а-яА-ЯёЁ]", "", base_name)
    base_name = base_name[:24] if base_name else f"user_{client.id}"

    identity = client.telegram_id or (client.public_id[:10] if client.public_id else f"id{client.id}")
    identity = re.sub(r"[^a-zA-Z0-9_]", "", identity)

    return f"cl_{identity}_{base_name}"


def generate_happ_subscription_token() -> str:
    return secrets.token_urlsafe(24)


def build_happ_subscription_url(token: str) -> str:
    return f"{APP_BASE_URL}/sub/{token}"


def build_hiddify_import_url(subscription_url: str | None) -> str | None:
    if not subscription_url:
        return None
    return f"hiddify://install-sub?url={url_quote(subscription_url, safe='')}"


def build_happ_import_url(plain_subscription_url: str | None) -> str | None:
    if not plain_subscription_url:
        return None
    return f"happ://import?url={url_quote(plain_subscription_url, safe='')}"


def ensure_happ_subscription_for_client(client: Client) -> None:
    if not client.happ_subscription_token:
        client.happ_subscription_token = generate_happ_subscription_token()

    client.happ_subscription_url = build_happ_subscription_url(
        client.happ_subscription_token
    )


def is_client_subscription_active(client: Client) -> bool:
    if client.status != "active":
        return False
    if not client.is_active or not client.is_paid:
        return False
    if not client.paid_until:
        return False
    return client.paid_until > datetime.utcnow()


def build_node_config(node: VpnNode) -> NodeConfig:
    return NodeConfig(
        code=node.code,
        name=node.name,
        display_name=node.display_name,
        panel_url=node.panel_url,
        username=node.panel_username,
        password=node.panel_password,
        web_base_path=node.web_base_path or "",
        inbound_port=node.inbound_port,
        vless_domain=node.vless_domain,
        vless_public_port=node.vless_public_port,
        vless_path=node.vless_path,
        vless_security=node.vless_security,
        vless_sni=node.vless_sni,
    )


async def _serialize_legacy_vpn_access(client: Client) -> dict:
    subscription_active = is_client_subscription_active(client)
    manual_url = client.subscription_link
    servers = []

    if manual_url:
        servers.append(
            {
                "code": DEFAULT_NODE_CONFIG.code,
                "name": DEFAULT_NODE_CONFIG.name,
                "display_name": DEFAULT_NODE_CONFIG.display_name,
                "domain": DEFAULT_NODE_CONFIG.vless_domain,
                "manual_url": manual_url,
                "enabled": True,
            }
        )

    happ_import_url = build_happ_import_url(client.happ_subscription_url)

    return {
        "access": bool(client.xui_uuid and client.subscription_link),
        "subscription_active": subscription_active,
        "expires_at": client.paid_until.isoformat() if client.paid_until else None,
        "vpn": {
            "type": "xray_vless",
            "subscription_url": client.happ_subscription_url,
            "happ_import_url": happ_import_url or client.happ_subscription_url,
            "hiddify_import_url": build_hiddify_import_url(client.happ_subscription_url),
            "manual_url": manual_url,
            "manual_urls": [manual_url] if manual_url else [],
            "servers": servers,
            "supports": SUPPORTED_PLATFORMS,
        },
    }


async def _load_active_nodes(session: AsyncSession) -> list[VpnNode]:
    try:
        result = await session.execute(
            select(VpnNode)
            .where(VpnNode.is_active.is_(True))
            .order_by(VpnNode.sort_order.asc(), VpnNode.id.asc())
        )
        return list(result.scalars().all())
    except SQLAlchemyError:
        logger.exception("Failed to load vpn_nodes, falling back to legacy single-node mode")
        return []


async def _load_client_access_pairs(
    session: AsyncSession,
    client_id: int,
    *,
    active_nodes_only: bool = False,
    enabled_only: bool = False,
) -> list[tuple[ClientVpnAccess, VpnNode]]:
    try:
        query = (
            select(ClientVpnAccess, VpnNode)
            .join(VpnNode, VpnNode.id == ClientVpnAccess.node_id)
            .where(ClientVpnAccess.client_id == client_id)
            .order_by(VpnNode.sort_order.asc(), VpnNode.id.asc(), ClientVpnAccess.id.asc())
        )

        if active_nodes_only:
            query = query.where(VpnNode.is_active.is_(True))
        if enabled_only:
            query = query.where(ClientVpnAccess.is_enabled.is_(True))

        result = await session.execute(query)
        return list(result.all())
    except SQLAlchemyError:
        logger.exception("Failed to load client_vpn_access, falling back to legacy single-node mode")
        return []


async def _get_or_create_client_node_access(
    session: AsyncSession,
    client_id: int,
    node_id: int,
) -> ClientVpnAccess:
    result = await session.execute(
        select(ClientVpnAccess).where(
            ClientVpnAccess.client_id == client_id,
            ClientVpnAccess.node_id == node_id,
        )
    )
    access = result.scalar_one_or_none()
    if access:
        return access

    access = ClientVpnAccess(
        client_id=client_id,
        node_id=node_id,
        is_enabled=True,
    )
    session.add(access)
    await session.flush()
    return access


async def _sync_legacy_fields(session: AsyncSession, client: Client) -> None:
    pairs = await _load_client_access_pairs(
        session,
        client.id,
        active_nodes_only=True,
        enabled_only=True,
    )

    if not pairs:
        client.xui_uuid = None
        client.xui_email = None
        client.subscription_link = None
        client.updated_at = datetime.utcnow()
        return

    primary_access, _primary_node = pairs[0]
    client.login = primary_access.xui_email or client.login
    client.xui_uuid = primary_access.xui_uuid
    client.xui_email = primary_access.xui_email
    client.subscription_link = primary_access.subscription_link
    client.updated_at = datetime.utcnow()


async def _collect_subscription_links(session: AsyncSession, client: Client) -> list[str]:
    pairs = await _load_client_access_pairs(
        session,
        client.id,
        active_nodes_only=True,
        enabled_only=True,
    )
    links = [
        access.subscription_link.strip()
        for access, _node in pairs
        if access.subscription_link and access.subscription_link.strip()
    ]

    if links:
        return links

    if client.subscription_link:
        return [client.subscription_link.strip()]

    return []


async def _serialize_multi_node_vpn_access(session: AsyncSession, client: Client) -> dict:
    subscription_active = is_client_subscription_active(client)
    pairs = await _load_client_access_pairs(
        session,
        client.id,
        active_nodes_only=True,
        enabled_only=True,
    )

    if not pairs:
        return await _serialize_legacy_vpn_access(client)

    servers = []
    manual_urls = []

    for access, node in pairs:
        if not access.subscription_link:
            continue

        manual_urls.append(access.subscription_link)
        servers.append(
            {
                "code": node.code,
                "name": node.name,
                "display_name": node.display_name,
                "country_code": node.country_code,
                "domain": node.vless_domain,
                "public_port": node.vless_public_port,
                "path": node.vless_path,
                "security": node.vless_security,
                "sni": node.vless_sni,
                "manual_url": access.subscription_link,
                "enabled": bool(access.is_enabled and node.is_active),
            }
        )

    manual_url = manual_urls[0] if manual_urls else None
    happ_import_url = build_happ_import_url(client.happ_subscription_url)

    return {
        "access": bool(manual_urls),
        "subscription_active": subscription_active,
        "expires_at": client.paid_until.isoformat() if client.paid_until else None,
        "vpn": {
            "type": "xray_vless",
            "subscription_url": client.happ_subscription_url,
            "happ_import_url": happ_import_url or client.happ_subscription_url,
            "hiddify_import_url": build_hiddify_import_url(client.happ_subscription_url),
            "manual_url": manual_url,
            "manual_urls": manual_urls,
            "servers": servers,
            "supports": SUPPORTED_PLATFORMS,
        },
    }


async def ensure_client_exists(telegram_id: str, full_name: str) -> Client:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == str(telegram_id))
        )
        client = result.scalar_one_or_none()

        if client is None:
            client = Client(
                telegram_id=str(telegram_id),
                full_name=full_name,
                is_active=False,
                is_paid=False,
                created_via="telegram",
                status="active",
            )
            session.add(client)
            await session.commit()
            await session.refresh(client)

        return client


async def get_client_by_telegram_id(telegram_id: str) -> Optional[Client]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.telegram_id == str(telegram_id))
        )
        return result.scalar_one_or_none()


async def get_client_by_id(client_id: int) -> Optional[Client]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id)
        )
        return result.scalar_one_or_none()


async def get_client_subscription_links_by_client_id(client_id: int) -> list[str]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if not client:
            return []
        return await _collect_subscription_links(session, client)


async def get_client_vpn_access_by_client_id(client_id: int) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()
        if not client:
            return None
        return await _serialize_multi_node_vpn_access(session, client)


async def get_client_vpn_access_by_telegram_id(telegram_id: str) -> Optional[dict]:
    client = await get_client_by_telegram_id(telegram_id)
    if not client:
        return None
    return await get_client_vpn_access_by_client_id(client.id)


async def _update_existing_access_for_node(
    session: AsyncSession,
    client: Client,
    node: VpnNode,
    access: ClientVpnAccess,
) -> bool:
    if not client.paid_until:
        logger.warning("Cannot update access: paid_until is empty for client_id=%s", client.id)
        return False

    paid_until_ts_ms = int(client.paid_until.timestamp() * 1000)

    if not access.xui_email and not access.xui_uuid:
        return False

    async with VLESSManager(node_config=build_node_config(node)) as manager:
        try:
            updated = await manager.enable_client(
                email=access.xui_email,
                client_uuid=access.xui_uuid,
                expiry_time_ms=paid_until_ts_ms,
                total_gb=0,
            )
        except TypeError:
            logger.exception("enable_client signature mismatch")
            updated = False
        except Exception:
            logger.exception(
                "Failed to enable/update existing client access client_id=%s node=%s",
                client.id,
                node.code,
            )
            updated = False

        if updated:
            refreshed_link = await manager.get_client_link(
                email=access.xui_email,
                client_uuid=access.xui_uuid,
            )
            if refreshed_link:
                access.subscription_link = refreshed_link
            access.is_enabled = True
            access.updated_at = datetime.utcnow()
            await session.flush()
            return True

    return False


async def _ensure_access_for_node(
    session: AsyncSession,
    client: Client,
    node: VpnNode,
) -> bool:
    if not client.paid_until:
        logger.warning("paid_until is empty for client_id=%s", client.id)
        return False

    access = await _get_or_create_client_node_access(session, client.id, node.id)
    paid_until_ts_ms = int(client.paid_until.timestamp() * 1000)
    xui_email = access.xui_email or client.login or make_xui_email(client)
    external_identity = client.telegram_id or f"client_{client.id}"

    if access.xui_email or access.xui_uuid:
        synced = await _update_existing_access_for_node(session, client, node, access)
        if synced:
            return True

    async with VLESSManager(node_config=build_node_config(node)) as manager:
        created = await manager.add_client(
            telegram_id=external_identity,
            full_name=client.full_name or client.email or xui_email,
            xui_email=xui_email,
            paid_until_ts_ms=paid_until_ts_ms,
            total_gb=0,
        )

    if not created:
        logger.error(
            "Failed to create client access for client_id=%s node=%s",
            client.id,
            node.code,
        )
        return False

    xui_uuid, xui_email, subscription_link = created
    access.xui_uuid = xui_uuid
    access.xui_email = xui_email
    access.subscription_link = subscription_link
    access.is_enabled = True
    access.updated_at = datetime.utcnow()
    await session.flush()
    return True


async def create_vpn_access_for_client_id(client_id: int) -> bool:
    logger.info("create_vpn_access_for_client_id start client_id=%s", client_id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id)
        )
        client = result.scalar_one_or_none()

        if client is None:
            logger.warning("Client not found for client_id=%s", client_id)
            return False

        if not client.paid_until:
            logger.warning("paid_until is empty for client_id=%s", client_id)
            return False

        ensure_happ_subscription_for_client(client)

        nodes = await _load_active_nodes(session)
        if not nodes:
            logger.warning("No active vpn_nodes found, legacy single-node mode remains active")
            if client.xui_uuid and client.subscription_link:
                client.updated_at = datetime.utcnow()
                await session.commit()
                return True
            return False

        ok = True
        for node in nodes:
            node_ok = await _ensure_access_for_node(session, client, node)
            ok = ok and node_ok

        await _sync_legacy_fields(session, client)
        await session.commit()
        return ok


async def create_vpn_access_for_client(telegram_id: str) -> bool:
    client = await get_client_by_telegram_id(telegram_id)
    if not client:
        logger.warning("Client not found for telegram_id=%s", telegram_id)
        return False
    return await create_vpn_access_for_client_id(client.id)


async def disable_vpn_access_for_client_id(client_id: int) -> bool:
    logger.info("disable_vpn_access_for_client_id start client_id=%s", client_id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id)
        )
        client = result.scalar_one_or_none()

        if client is None:
            logger.warning("Client not found for client_id=%s", client_id)
            return False

        pairs = await _load_client_access_pairs(session, client.id)
        if not pairs:
            logger.info("Client has no multi-node xray access client_id=%s", client_id)
            client.updated_at = datetime.utcnow()
            await session.commit()
            return True

        overall_ok = True

        for access, node in pairs:
            if not access.xui_email and not access.xui_uuid:
                access.is_enabled = False
                continue

            async with VLESSManager(node_config=build_node_config(node)) as manager:
                try:
                    disabled = await manager.disable_client(
                        email=access.xui_email,
                        client_uuid=access.xui_uuid,
                    )
                except TypeError:
                    logger.exception("disable_client signature mismatch")
                    disabled = False
                except Exception:
                    logger.exception(
                        "Failed to disable VPN access for client_id=%s node=%s",
                        client.id,
                        node.code,
                    )
                    disabled = False

            overall_ok = overall_ok and disabled
            if disabled:
                access.is_enabled = False
                access.updated_at = datetime.utcnow()

        await _sync_legacy_fields(session, client)
        await session.commit()
        return overall_ok


async def disable_vpn_access_for_client(telegram_id: str) -> bool:
    client = await get_client_by_telegram_id(telegram_id)
    if not client:
        logger.warning("Client not found for telegram_id=%s", telegram_id)
        return False
    return await disable_vpn_access_for_client_id(client.id)


async def sync_vpn_access_for_client_id(client_id: int) -> bool:
    client = await get_client_by_id(client_id)
    if not client:
        return False

    if is_client_subscription_active(client):
        return await create_vpn_access_for_client_id(client_id)

    return await disable_vpn_access_for_client_id(client_id)


async def sync_vpn_access_for_client(telegram_id: str) -> bool:
    client = await get_client_by_telegram_id(telegram_id)
    if not client:
        return False
    return await sync_vpn_access_for_client_id(client.id)
