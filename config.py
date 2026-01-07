import os
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv
from pathlib import Path

# Загружаем переменные окружения из .env файла
try:
    from dotenv import load_dotenv
    # Загружаем .env из корня проекта
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # python-dotenv не установлен, но это ок

@dataclass
class Config:
    # Пути к данным
    DATA_DIR: str = "data"
    VECTOR_DB_PATH: str = os.path.join(DATA_DIR, "vector_db")
    
    # Настройки обработки текста
    CHUNK_SIZE: int = 1000  # Размер чанка в символах
    CHUNK_OVERLAP: int = 200  # Перекрытие между чанками
    INCLUDE_TITLES: bool = True  # Добавлять заголовки в чанки
    MAX_TITLE_LENGTH: int = 100  # Максимальная длина заголовка в чанке
    
    # Настройки эмбеддингов
    EMBEDDING_MODEL: str = "text-embedding-ada-002"  # Модель для эмбеддингов
    EMBEDDING_DIMENSION: int = 1536  # Размерность эмбеддингов для ada-002
    
    # Настройки OpenRouter
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    
    # Модель для LLM
    LLM_MODEL: str = "meta-llama/llama-3.3-70b-instruct:free"
    
    # Настройки RAG
    RETRIEVER_K: int = 4  # Сколько чанков возвращать при поиске
    
    def __post_init__(self):
        # Автоматически создаем директории
        os.makedirs(self.DATA_DIR, exist_ok=True)
        os.makedirs(self.VECTOR_DB_PATH, exist_ok=True)
        
        # Получаем API ключ ТОЛЬКО из переменных окружения
        # Если ключ не установлен - будет ошибка при использовании
        self.OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

config = Config()