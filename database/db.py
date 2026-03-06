# database/db.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from .models import Base
from pathlib import Path
import config

# 🔥 Универсальная функция для получения абсолютного пути к БД
def get_database_path(db_url: str) -> str:
    """Преобразует относительный путь SQLite в абсолютный"""
    if not db_url.startswith('sqlite:///'):
        return db_url
    
    # Извлекаем путь после sqlite:///
    relative_path = db_url.replace('sqlite:///', '')
    
    # Если путь уже абсолютный (начинается с /)
    if relative_path.startswith('/'):
        return db_url
    
    # Преобразуем в абсолютный относительно корня проекта
    # __file__ = /home/konsta/Documents/v1/database/db.py
    # .parent.parent = /home/konsta/Documents/v1/
    project_root = Path(__file__).resolve().parent.parent
    absolute_path = project_root / relative_path
    
    # Создаём родительские директории если нужно
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    
    return f'sqlite:///{absolute_path}'

# Получаем правильный URL для подключения
DATABASE_URL = get_database_path(config.DATABASE_URL)

# Создание движка БД
engine = create_engine(
    DATABASE_URL,
    echo=config.DEBUG,
    future=True,
    connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}
)

# Создание сессии
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True
)

def get_db() -> Session:
    """Получить сессию базы данных (генератор)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    """Создать все таблицы в БД"""
    Base.metadata.create_all(bind=engine)

def get_db_session() -> Session:
    """Получить сессию (для разовых операций)"""
    return SessionLocal()
