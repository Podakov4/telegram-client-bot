from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)  # ✅ ДОБАВИТЬ ЭТУ СТРОКУ!
    full_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    login = Column(String, nullable=True, unique=True, index=True)
    notes = Column(Text, nullable=True)

    wireguard_public_key = Column(String, nullable=True)
    wireguard_config = Column(Text, nullable=True)

    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    last_seen = Column(DateTime, nullable=True)
    is_online = Column(Boolean, default=False)

    traffic_upload = Column(BigInteger, default=0)
    traffic_download = Column(BigInteger, default=0)

    connection_count = Column(Integer, default=0)
    subscription_end = Column(DateTime, nullable=True)