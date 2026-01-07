"""
Простой скрипт для запуска сервера - находится в КОРНЕ проекта
"""
import os
import sys
from pathlib import Path

# --- ВАЖНО: загружаем .env файл в самом начале ---
from dotenv import load_dotenv

# Загружаем .env из текущей директории (корня проекта)
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Загружены переменные окружения из {env_path}")
else:
    print("⚠️  Файл .env не найден!")
    print("   Использую системные переменные окружения...")

# Проверяем API ключ
api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    print("\n❌ ОШИБКА: OPENROUTER_API_KEY не установлен!")
    print("\nСоздайте файл .env в корне проекта с содержимым:")
    print("OPENROUTER_API_KEY=ваш_ключ_здесь")
    sys.exit(1)

# Показываем часть ключа для подтверждения
key_preview = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
print(f"🔑 API ключ: {key_preview}")

# Проверяем векторную БД
vector_db_path = Path(__file__).parent / "data" / "vector_db"
if not vector_db_path.exists():
    print("\n⚠️  ВНИМАНИЕ: Векторная база данных не найдена!")
    print(f"   Путь: {vector_db_path}")
    print("\nСначала создайте векторную базу:")
    print("  python src/create_vector_db_from_json.py")
    
    response = input("\nПродолжить без векторной БД? (y/n): ").strip().lower()
    if response != 'y':
        print("❌ Завершение работы...")
        sys.exit(1)

# --- ЗАПУСК СЕРВЕРА ---
print("\n" + "=" * 60)
print("🚀 ЗАПУСК NEoFLEX RAG QA API")
print("=" * 60)
print("Сервер будет доступен по адресам:")
print("  • API: http://localhost:8000")
print("  • Документация: http://localhost:8000/docs")
print("  • Состояние: http://localhost:8000/health")
print("\nНажмите Ctrl+C для остановки сервера")
print("=" * 60)

try:
    # Импортируем uvicorn
    import uvicorn
    
    # Запускаем сервер
    uvicorn.run(
        "src.api_server:app",  # Важно: указываем полный путь
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
    
except KeyboardInterrupt:
    print("\n\n👋 Сервер остановлен")
except Exception as e:
    print(f"\n❌ Ошибка при запуске сервера: {e}")
    import traceback
    traceback.print_exc()