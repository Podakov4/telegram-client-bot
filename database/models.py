# database/models.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Client(Base):
    """Модель клиента"""
    __tablename__ = 'clients'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    
    # WireGuard
    wireguard_public_key = Column(String, nullable=True)
    wireguard_ip = Column(String, nullable=True)
    wireguard_config = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<Client(id={self.id}, telegram_id={self.telegram_id}, name={self.full_name})>"
