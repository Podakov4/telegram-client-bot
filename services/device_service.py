from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AppSession, Client, Device, Plan


@dataclass
class DeviceLimitInfo:
    max_devices: int
    active_devices: int
    can_add_more: bool


class DeviceError(Exception):
    pass


class DeviceNotFoundError(DeviceError):
    pass


class DeviceAccessError(DeviceError):
    pass


class DeviceLimitExceededError(DeviceError):
    pass


class DeviceService:
    @staticmethod
    def _utcnow() -> datetime:
        return datetime.utcnow()

    @staticmethod
    async def list_devices(
        db: AsyncSession,
        client_id: int,
        include_revoked: bool = True,
    ) -> list[Device]:
        query = select(Device).where(Device.client_id == client_id)

        if not include_revoked:
            query = query.where(Device.is_revoked.is_(False))

        query = query.order_by(Device.created_at.desc())

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_device_by_id(
        db: AsyncSession,
        client_id: int,
        device_id: int,
    ) -> Device:
        result = await db.execute(
            select(Device).where(
                Device.id == device_id,
                Device.client_id == client_id,
            )
        )
        device = result.scalar_one_or_none()
        if not device:
            raise DeviceNotFoundError("Device not found")
        return device

    @staticmethod
    async def get_device_by_uid(
        db: AsyncSession,
        client_id: int,
        device_uid: str,
    ) -> Optional[Device]:
        result = await db.execute(
            select(Device).where(
                Device.client_id == client_id,
                Device.device_uid == device_uid,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def count_active_devices(
        db: AsyncSession,
        client_id: int,
    ) -> int:
        result = await db.execute(
            select(func.count(Device.id)).where(
                Device.client_id == client_id,
                Device.is_active.is_(True),
                Device.is_revoked.is_(False),
            )
        )
        count = result.scalar_one()
        return int(count or 0)

    @staticmethod
    async def get_max_devices_for_client(
        db: AsyncSession,
        client: Client,
        default_max_devices: int = 3,
    ) -> int:
        """
        Пока fallback-логика простая:
        1) если в notes есть max_devices=...
        2) если позже появится связка с Plan, можно подключить её тут
        3) иначе default_max_devices
        """
        if client.notes:
            for line in client.notes.splitlines():
                raw = line.strip()
                if raw.lower().startswith("max_devices="):
                    _, value = raw.split("=", 1)
                    try:
                        parsed = int(value.strip())
                        if parsed > 0:
                            return parsed
                    except ValueError:
                        pass

        # Заготовка на будущее: если появится реальная связка клиента с тарифом/планом,
        # сюда легко добавить lookup по Plan.
        _ = Plan

        return default_max_devices

    @staticmethod
    async def get_device_limit_info(
        db: AsyncSession,
        client: Client,
        default_max_devices: int = 3,
    ) -> DeviceLimitInfo:
        max_devices = await DeviceService.get_max_devices_for_client(
            db=db,
            client=client,
            default_max_devices=default_max_devices,
        )
        active_devices = await DeviceService.count_active_devices(
            db=db,
            client_id=client.id,
        )

        return DeviceLimitInfo(
            max_devices=max_devices,
            active_devices=active_devices,
            can_add_more=active_devices < max_devices,
        )

    @staticmethod
    async def ensure_device_slot_available(
        db: AsyncSession,
        client: Client,
        device_uid: str,
        default_max_devices: int = 3,
    ) -> None:
        existing_device = await DeviceService.get_device_by_uid(
            db=db,
            client_id=client.id,
            device_uid=device_uid,
        )

        if existing_device and not existing_device.is_revoked:
            return

        limit_info = await DeviceService.get_device_limit_info(
            db=db,
            client=client,
            default_max_devices=default_max_devices,
        )

        if not limit_info.can_add_more:
            raise DeviceLimitExceededError(
                f"Device limit exceeded: {limit_info.active_devices}/{limit_info.max_devices}"
            )

    @staticmethod
    async def register_or_update_device(
        db: AsyncSession,
        client: Client,
        device_uid: str,
        platform: str,
        device_name: Optional[str] = None,
        app_version: Optional[str] = None,
        os_version: Optional[str] = None,
        default_max_devices: int = 3,
    ) -> Device:
        await DeviceService.ensure_device_slot_available(
            db=db,
            client=client,
            device_uid=device_uid,
            default_max_devices=default_max_devices,
        )

        result = await db.execute(
            select(Device).where(Device.device_uid == device_uid)
        )
        device = result.scalar_one_or_none()

        now = DeviceService._utcnow()

        if device:
            if device.client_id != client.id:
                raise DeviceAccessError("Device belongs to another client")

            device.platform = platform
            device.device_name = device_name
            device.app_version = app_version
            device.os_version = os_version
            device.is_active = True
            device.is_revoked = False
            device.last_seen_at = now

            await db.commit()
            await db.refresh(device)
            return device

        device = Device(
            client_id=client.id,
            device_uid=device_uid,
            platform=platform,
            device_name=device_name,
            app_version=app_version,
            os_version=os_version,
            is_active=True,
            is_revoked=False,
            last_seen_at=now,
        )
        db.add(device)
        await db.commit()
        await db.refresh(device)
        return device

    @staticmethod
    async def touch_device(
        db: AsyncSession,
        client_id: int,
        device_id: int,
    ) -> Optional[Device]:
        device = await DeviceService.get_device_by_id(
            db=db,
            client_id=client_id,
            device_id=device_id,
        )
        device.last_seen_at = DeviceService._utcnow()
        await db.commit()
        await db.refresh(device)
        return device

    @staticmethod
    async def revoke_device(
        db: AsyncSession,
        client_id: int,
        device_id: int,
    ) -> Device:
        device = await DeviceService.get_device_by_id(
            db=db,
            client_id=client_id,
            device_id=device_id,
        )

        now = DeviceService._utcnow()

        device.is_active = False
        device.is_revoked = True
        device.last_seen_at = now

        result = await db.execute(
            select(AppSession).where(
                AppSession.device_id == device.id,
                AppSession.revoked_at.is_(None),
            )
        )
        sessions = result.scalars().all()
        for session in sessions:
            session.revoked_at = now

        await db.commit()
        await db.refresh(device)
        return device

    @staticmethod
    async def revoke_all_devices(
        db: AsyncSession,
        client_id: int,
        exclude_device_id: Optional[int] = None,
    ) -> int:
        query = select(Device).where(
            Device.client_id == client_id,
            Device.is_revoked.is_(False),
        )

        if exclude_device_id is not None:
            query = query.where(Device.id != exclude_device_id)

        result = await db.execute(query)
        devices = result.scalars().all()

        now = DeviceService._utcnow()
        revoked_count = 0

        for device in devices:
            device.is_active = False
            device.is_revoked = True
            device.last_seen_at = now
            revoked_count += 1

            sessions_result = await db.execute(
                select(AppSession).where(
                    AppSession.device_id == device.id,
                    AppSession.revoked_at.is_(None),
                )
            )
            sessions = sessions_result.scalars().all()
            for session in sessions:
                session.revoked_at = now

        if revoked_count:
            await db.commit()

        return revoked_count

    @staticmethod
    def serialize_device(device: Device) -> dict:
        return {
            "id": device.id,
            "device_uid": device.device_uid,
            "platform": device.platform,
            "device_name": device.device_name,
            "app_version": device.app_version,
            "os_version": device.os_version,
            "is_active": device.is_active,
            "is_revoked": device.is_revoked,
            "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
            "created_at": device.created_at.isoformat() if device.created_at else None,
            "updated_at": device.updated_at.isoformat() if device.updated_at else None,
        }