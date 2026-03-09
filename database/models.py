from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


class Client(Base):
    """Модель клиента"""
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint('telegram_id'),
        UniqueConstraint('login'),
    )

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    login = Column(String, unique=True, index=True, nullable=True)
    subscription_link = Column(Text, nullable=True)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Client(id={self.id}, telegram_id='{self.telegram_id}', login='{self.login}')>"