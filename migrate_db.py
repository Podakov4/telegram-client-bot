# migrate_db.py
from sqlalchemy import inspect, text  # ← text должен быть здесь!
from database import engine

def migrate_database():
    print("🔍 Подключение к базе данных...")
    
    with engine.connect() as conn:
        inspector = inspect(engine)
        existing_columns = [col['name'] for col in inspector.get_columns('clients')]
        
        print(f"✅ Найдено колонок: {len(existing_columns)}")
        
        new_fields = {
            'last_seen': 'DATETIME',
            'is_online': 'BOOLEAN',
            'traffic_upload': 'BIGINT',
            'traffic_download': 'BIGINT',
            'connection_count': 'INTEGER',
            'subscription_end': 'DATETIME'
        }
        
        for col_name, col_type in new_fields.items():
            if col_name not in existing_columns:
                sql = f'ALTER TABLE clients ADD COLUMN {col_name} {col_type}'
                print(f"➕ Добавляем поле: {col_name} ({col_type})")
                
                # 🔥 ВАЖНО: Оборачиваем в text()
                conn.execute(text(sql))  # ← text() здесь!
            else:
                print(f"⏭️  Поле {col_name} уже существует")
        
        conn.commit()
    
    print("\n🎉 Миграция завершена!")

if __name__ == "__main__":
    try:
        migrate_database()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
