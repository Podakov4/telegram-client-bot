# test_db.py
from database import create_tables, get_db_session, Client

def test_database():
    """Тест подключения к БД"""
    print("🔧 Создание таблиц...")
    create_tables()
    print("✅ Таблицы созданы!")
    
    print("\n🔍 Проверка подключения...")
    db = get_db_session()
    
    # Попробуй добавить тестового клиента
    test_client = Client(
        telegram_id="999999999",
        full_name="Тестовый Клиент",
        username="test_user",
        phone="+1234567890",
        email="test@example.com"
    )
    
    db.add(test_client)
    db.commit()
    db.refresh(test_client)
    
    print(f"✅ Клиент добавлен с ID: {test_client.id}")
    
    # Получи всех клиентов
    clients = db.query(Client).all()
    print(f"📊 Всего клиентов в БД: {len(clients)}")
    
    db.delete(test_client)
    db.commit()
    db.close()
    
    print("✅ Тест завершён успешно!")

if __name__ == "__main__":
    test_database()
