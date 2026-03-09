from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


class Client(Base):
    """Модель клиента (строго по структуре реальной БД)"""
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint('telegram_id'),
        UniqueConstraint('login'),
    )

    # Основные поля (есть в БД)
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)

    # Login для VLESS (есть в БД)
    login = Column(String, unique=True, index=True, nullable=True)

    # Ссылка на конфиг (в БД называется subscription_link, а не wireguard_config!)
    subscription_link = Column(Text, nullable=True)

    # Статусы (есть в БД)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    # Заметки (есть в БД)
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Client(id={self.id}, telegram_id='{self.telegram_id}', login='{self.login}')>"