#!/usr/bin/env python3
"""Миграция: добавляет колонку login и копирует туда email"""

import sys
import os
import sqlite3
import re
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


def migrate():
    """Добавить колонку login и заполнить её данными из username/email"""

    print("=" * 60)
    print("🔧 ЗАПУСК МИГРАЦИИ: Добавление колонки 'login'")
    print("=" * 60)

    db_path = os.path.join(BASE_DIR, "database", "clients.db")

    if not os.path.exists(db_path):
        logger.error(f"❌ База данных не найдена: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Проверяем существует ли колонка
        cursor.execute("PRAGMA table_info(clients)")
        columns = [col[1] for col in cursor.fetchall()]

        if "login" in columns:
            logger.info("✅ Колонка 'login' уже существует!")
            return

        logger.warning("⚠️ Колонка 'login' не найдена — добавляю её...")

        # Добавляем колонку
        cursor.execute("""
            ALTER TABLE clients ADD COLUMN login VARCHAR DEFAULT NULL
        """)
        conn.commit()
        logger.info("✅ Колонка добавлена успешно!")

        # Заполняем данными
        logger.info("Заполнение колонки login данными...")

        cursor.execute("SELECT id, full_name, username, email FROM clients")
        rows = cursor.fetchall()

        update_count = 0
        for row_id, name, uname, email in rows:
            # Приоритет: username > email > full_name
            if uname and uname.strip():
                new_login = uname.strip().lower()
            elif email and email.strip():
                new_login = email.strip().lower()
            elif name and name.strip():
                new_login = name.strip().lower().replace(" ", "_").replace("ё", "е")
            else:
                new_login = f"user_{row_id}"

            # Чистим от спецсимволов
            new_login = re.sub(r'[^a-zа-яё0-9_]', '', new_login)

            if not new_login:
                new_login = f"user_{row_id}"

            cursor.execute("UPDATE clients SET login = ? WHERE id = ?", (new_login, row_id))
            update_count += 1

        conn.commit()
        logger.info(f"✅ Обновлено {update_count} записей")

        # Показываем тестовые записи
        cursor.execute("SELECT id, login FROM clients LIMIT 5")
        test_rows = cursor.fetchall()

        logger.info("Тестовые записи:")
        for test_id, test_login in test_rows:
            logger.info(f"   ID={test_id}, login='{test_login}'")

        logger.info("\n🎉 Миграция завершена успешно!")

    except Exception as e:
        logger.error(f"❌ Ошибка миграции: {e}")
        conn.rollback()
    finally:
        conn.close()

    print("=" * 60)


if __name__ == "__main__":
    migrate()