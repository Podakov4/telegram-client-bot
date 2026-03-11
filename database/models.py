from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from database.db import Base


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)

    telegram_id = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=True)

    login = Column(String, unique=True, nullable=True)

    xui_uuid = Column(String, unique=True, nullable=True)
    xui_email = Column(String, unique=True, nullable=True)

    subscription_link = Column(Text, nullable=True)

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

    history = relationship("SubscriptionHistory", back_populates="client")


class SubscriptionHistory(Base):
    __tablename__ = "subscription_history"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)

    plan_code = Column(String, nullable=False)   # trial_7d / 1m / 3m / 12m
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
    telegram_id = Column(String, nullable=False, index=True)
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