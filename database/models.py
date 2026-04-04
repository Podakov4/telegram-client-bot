from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database.db import Base


def generate_public_id() -> str:
    return uuid4().hex


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)

    # Identity
    telegram_id = Column(String, unique=True, nullable=True, index=True)
    full_name = Column(String, nullable=True)
    login = Column(String, unique=True, nullable=True)

    # Cross-platform identity fields
    public_id = Column(String, unique=True, nullable=False, index=True, default=generate_public_id)
    email = Column(String, unique=True, nullable=True, index=True)
    status = Column(String, nullable=False, default="active")  # active / blocked / deleted
    created_via = Column(String, nullable=False, default="telegram")  # telegram / email / admin / etc.
    default_language = Column(String, nullable=True, default="ru")
    last_login_at = Column(DateTime, nullable=True)

    # Legacy single-node fields kept for backward compatibility.
    # Primary node values are mirrored here so old bot/app code keeps working.
    xui_uuid = Column(String, unique=True, nullable=True)
    xui_email = Column(String, unique=True, nullable=True)
    subscription_link = Column(Text, nullable=True)

    happ_subscription_token = Column(String, unique=True, nullable=True, index=True)
    happ_subscription_url = Column(Text, nullable=True)

    is_active = Column(Boolean, default=False, nullable=False)
    is_paid = Column(Boolean, default=False, nullable=False)

    paid_until = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    last_expiring_notice_at = Column(DateTime, nullable=True)
    last_expired_notice_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    history = relationship(
        "SubscriptionHistory",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    devices = relationship(
        "Device",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    login_codes = relationship(
        "LoginCode",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    email_login_codes = relationship(
        "EmailLoginCode",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    app_sessions = relationship(
        "AppSession",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    vpn_accesses = relationship(
        "ClientVpnAccess",
        back_populates="client",
        cascade="all, delete-orphan",
    )


class VpnNode(Base):
    __tablename__ = "vpn_nodes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False, index=True)  # nl / de
    name = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    country_code = Column(String, nullable=True)

    panel_url = Column(String, nullable=False)
    panel_username = Column(String, nullable=False)
    panel_password = Column(String, nullable=False)
    web_base_path = Column(String, nullable=True)
    inbound_port = Column(Integer, nullable=False)

    vless_domain = Column(String, nullable=False)
    vless_public_port = Column(Integer, nullable=False)
    vless_path = Column(String, nullable=False)
    vless_security = Column(String, nullable=False, default="tls")
    vless_sni = Column(String, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    client_accesses = relationship(
        "ClientVpnAccess",
        back_populates="node",
        cascade="all, delete-orphan",
    )


class ClientVpnAccess(Base):
    __tablename__ = "client_vpn_access"
    __table_args__ = (
        UniqueConstraint("client_id", "node_id", name="uq_client_vpn_access_client_node"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    node_id = Column(Integer, ForeignKey("vpn_nodes.id"), nullable=False, index=True)

    xui_uuid = Column(String, nullable=True, index=True)
    xui_email = Column(String, nullable=True, index=True)
    subscription_link = Column(Text, nullable=True)

    is_enabled = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    client = relationship("Client", back_populates="vpn_accesses")
    node = relationship("VpnNode", back_populates="client_accesses")


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)

    duration_days = Column(Integer, nullable=False)
    max_devices = Column(Integer, default=1, nullable=False)
    traffic_limit_gb = Column(Integer, nullable=True)

    is_trial = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)

    device_uid = Column(String, unique=True, nullable=False, index=True)
    platform = Column(String, nullable=False, index=True)  # android / ios / windows / macos / linux / web
    device_name = Column(String, nullable=True)
    app_version = Column(String, nullable=True)
    os_version = Column(String, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)

    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    client = relationship("Client", back_populates="devices")
    sessions = relationship(
        "AppSession",
        back_populates="device",
        cascade="all, delete-orphan",
    )


class LoginCode(Base):
    __tablename__ = "login_codes"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)

    code = Column(String, unique=True, nullable=False, index=True)
    platform = Column(String, nullable=True)  # android / ios / windows / macos / any
    device_uid = Column(String, nullable=True)

    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    client = relationship("Client", back_populates="login_codes")


class EmailLoginCode(Base):
    __tablename__ = "email_login_codes"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)

    email = Column(String, nullable=False, index=True)
    code_hash = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    client = relationship("Client", back_populates="email_login_codes")


class AppSession(Base):
    __tablename__ = "app_sessions"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)

    refresh_token_hash = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)

    client = relationship("Client", back_populates="app_sessions")
    device = relationship("Device", back_populates="sessions")


class SubscriptionHistory(Base):
    __tablename__ = "subscription_history"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)

    plan_code = Column(String, nullable=False)
    is_trial = Column(Boolean, default=False, nullable=False)

    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    notes = Column(Text, nullable=True)

    client = relationship("Client", back_populates="history")


class YooKassaPayment(Base):
    __tablename__ = "yookassa_payments"

    id = Column(Integer, primary_key=True, index=True)
    external_payment_id = Column(String, unique=True, nullable=False, index=True)

    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    telegram_id = Column(String, nullable=True, index=True)

    months = Column(Integer, nullable=False)
    amount = Column(String, nullable=False)

    status = Column(String, default="pending", nullable=False)
    is_processed = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    processed_at = Column(DateTime, nullable=True)
