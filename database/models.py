from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
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

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )