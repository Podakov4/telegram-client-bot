# database/models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    wireguard_public_key = Column(String, nullable=True)  # Теперь хранит UUID
    wireguard_config = Column(Text, nullable=True)  # Теперь хранит VLESS ссылку
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_seen = Column(DateTime, nullable=True)  # Последнее подключение
    is_online = Column(Boolean, default=False)  # Онлайн сейчас
    # Трафик (в байтах)
    traffic_upload = Column(BigInteger, default=0)  # Отправлено
    traffic_download = Column(BigInteger, default=0)  # Получено
    # Подключения
    connection_count = Column(Integer, default=0)  # Всего подключений
    # Срок подписки
    subscription_end = Column(DateTime, nullable=True)  # Дата окончания