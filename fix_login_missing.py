# !/usr/bin/env python3
"""Заполнение пропущенных значений login для клиентов базы данных"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from database import get_db_session, Client
import re


def clean_value(value):
    """Убираем спецсимволы и приводим к lower"""
    if not value:
        return None
    value = str(value).lower()
    value = re.sub(r'[^a-zа-яё0-9_]', '', value)
    return value.strip() if value else None


print("=" * 70)
print("🔧 ЗАПОЛНЕНИЕ ПРОПУЩЕННЫХ LOGIN")
print("=" * 70)

db = get_db_session()
try:
    clients = db.query(Client).all()

    updated_count = 0
    skipped_count = 0

    print(f"\n[1] Проверяем {len(clients)} клиентов...\n")

    for c in clients:
        current_login = clean_value(c.login)

        if current_login and len(current_login) > 0:
            skipped_count += 1
            continue

        # Приоритет заполнения login:
        # 1. email (если есть) → очищаем от спецсимволов
        # 2. username → очищаем от пробелов
        # 3. telegram_id → используется как fallback
        # 4. full_name → заменяем пробелы на underscore

        new_login = None

        # Пытаемся взять email
        if hasattr(c, 'email') and c.email:
            new_login = clean_value(c.email)

        # Если нет email или он пустой, пробуем username
        elif hasattr(c, 'username') and c.username:
            new_login = clean_value(c.username)

        # Если нет username, пробуем telegram_id
        elif hasattr(c, 'telegram_id') and c.telegram_id:
            tg_id = str(c.telegram_id)
            if tg_id.isdigit():
                # Для цифровых ID используем format
                new_login = f"user_{tg_id}"
            else:
                new_login = clean_value(tg_id)

        # Fallback — full_name
        elif hasattr(c, 'full_name') and c.full_name:
            new_login = c.full_name.lower().replace(' ', '_').replace('ё', 'е')
            new_login = re.sub(r'[^a-zа-яё0-9_]', '', new_login)

        # Ultimate fallback
        if not new_login:
            new_login = f"user_{c.id}_{skipped_count}"

        # Обновляем клиента
        old_login = c.login or "(пусто)"
        c.login = new_login
        updated_count += 1

        print(f"[{c.id}] {c.full_name or 'Без имени':<30}")
        print(f"     Старый: '{old_login}' → Новый: '{new_login}'")

    if updated_count > 0:
        db.commit()
        print(f"\n✅ Обновлено {updated_count} записей")
        print(f"⏸️ Пропущено {skipped_count} (у которых был login)")
    else:
        print(f"\n⚠️ Изменений не потребовалось")

except Exception as e:
    print(f"\n❌ Ошибка: {e}")
    import traceback

    traceback.print_exc()
    db.rollback()
finally:
    db.close()

print("\n" + "=" * 70)
print("ОКОНЧАНИЕ МИГРАЦИИ")
print("=" * 70)