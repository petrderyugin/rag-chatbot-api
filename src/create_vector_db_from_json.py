import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
from typing import List
from langchain_core.documents import Document

from config import config
from src.text_processor import TextProcessor
from src.vector_store_manager import HybridSearchVectorStoreManager

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_documents_from_json_correctly(json_path: str) -> List[Document]:
    """Правильная загрузка документов из JSON с подготовкой заголовков"""
    logger.info(f"Загружаю документы из {json_path}")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        pages = json.load(f)
    
    documents = []
    for page in pages:
        # Проверяем, есть ли контент
        if not page.get('content') or len(page['content'].strip()) < 50:
            logger.warning(f"Пропускаю страницу с малым контентом: {page['url']}")
            continue
        
        # Сохраняем полный заголовок, обрезка будет в TextProcessor
        title = page.get('title', 'Без названия')
        
        # Создаем документ
        doc = Document(
            page_content=page['content'],
            metadata={
                'url': page['url'],
                'state': page['state'],
                'original_title': title,  # Полный заголовок
                'characters': len(page['content']),
                'source': 'crawled_data.json'
            }
        )
        documents.append(doc)
    
    logger.info(f"Загружено {len(documents)} документов")
    return documents

def main():
    """Создание векторной базы ТОЛЬКО из структурированного JSON"""
    logger.info("=" * 60)
    logger.info("СОЗДАНИЕ ВЕКТОРНОЙ БАЗЫ ИЗ JSON (С ЗАГОЛОВКАМИ)")
    logger.info("=" * 60)
    
    # 1. Инициализируем процессор с заголовками
    processor = TextProcessor(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        include_title=config.INCLUDE_TITLES,
        max_title_length=config.MAX_TITLE_LENGTH  # Передаем конфиг
    )
    
    # 2. Загружаем документы из JSON
    documents = load_documents_from_json_correctly("data/crawled_data.json")
    
    # 3. Создаем чанки из КАЖДОГО документа отдельно
    logger.info("Создание чанков с заголовками...")
    all_chunks = []
    
    for i, doc in enumerate(documents):
        # Создаем чанки для каждого документа
        chunks = processor.create_chunks(doc.page_content, doc.metadata)
        all_chunks.extend(chunks)
        
        if (i + 1) % 50 == 0:
            logger.info(f"Обработано {i+1}/{len(documents)} страниц, создано {len(all_chunks)} чанков")
    
    logger.info(f"Всего создано {len(all_chunks)} чанков из {len(documents)} страниц")
    
    # 4. Проверяем, что заголовки добавлены
    if all_chunks:
        logger.info("\nПроверка добавления заголовков:")
        for i, chunk in enumerate(all_chunks[:3]):  # Первые 3 чанка
            content = chunk.page_content
            logger.info(f"Чанк {i+1} первые 150 символов: {content[:150]}...")
    
    # 5. Создаем менеджер векторной базы
    logger.info("Инициализация менеджера векторной базы...")
    manager = HybridSearchVectorStoreManager(use_local_embeddings=True)
    
    # Удаляем старую векторную базу (если есть)
    logger.info("Удаляю старую векторную базу...")
    manager.delete_vector_store()
    
    # 6. Создаем новую векторную базу
    logger.info("Создание новой векторной базы с заголовками...")
    vector_store = manager.create_vector_store(all_chunks, persist=True)
    
    # 7. Тестируем
    logger.info("\n" + "=" * 60)
    logger.info("ТЕСТИРОВАНИЕ ПОИСКА С ЗАГОЛОВКАМИ")
    logger.info("=" * 60)
    
    test_queries = [
        "Какие решения на основе искусственного интеллекта?",
        "Услуги data science Neoflex",
        "Клиенты компании",
        "Адреса офисов Neoflex"
    ]
    
    for query in test_queries:
        logger.info(f"\nЗапрос: '{query}'")
        results = manager.search_similar(query, k=2)
        
        for i, doc in enumerate(results):
            logger.info(f"  Результат {i+1}: {doc.page_content[:200]}...")
            logger.info(f"    URL: {doc.metadata.get('url', 'N/A')}")
    
    # 8. Информация о векторной базе
    info = manager.get_collection_info()
    logger.info(f"\nИнформация о векторной базе: {info}")
    
    logger.info("\nГотово! Векторная база создана корректно.")

if __name__ == "__main__":
    main()