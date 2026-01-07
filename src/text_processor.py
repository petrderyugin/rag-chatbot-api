import re
import hashlib
from typing import List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
import logging

logger = logging.getLogger(__name__)

class TextProcessor:
    """Профессиональный обработчик текста для RAG"""
    
    def __init__(self, chunk_size: int = 600, chunk_overlap: int = 150, 
                 include_title: bool = True, max_title_length: int = 60):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.include_title = include_title
        self.max_title_length = max_title_length
        
        # Инициализируем сплиттер с поддержкой русского языка
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=[
                "\n\n", "\n", ". ", "! ", "? ", "; ", ": ", ", ", " ", ""
            ],
            keep_separator=True
        )
    
    def clean_text(self, text: str) -> str:
        """Очистка текста от лишних символов и нормализация"""
        # Убираем лишние пробелы и переносы строк
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n+', '\n', text)
        
        # Нормализуем кавычки и тире
        replacements = {
            '«': '"', '»': '"', '„': '"', '“': '"',
            '—': '-', '–': '-', '‒': '-',
            '…': '...'
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text.strip()
    
    def _prepare_title(self, metadata: Dict[str, Any]) -> str:
        """Подготавливаем заголовок для добавления в чанк"""
        if not self.include_title:
            return ""
        
        # Пробуем получить заголовок из разных полей
        title = metadata.get('short_title') or metadata.get('original_title') or metadata.get('title', '')
        
        if not title:
            return ""
        
        # Обрезаем до максимальной длины
        if len(title) > self.max_title_length:
            title = title[:self.max_title_length-3] + "..."
        
        # Форматируем заголовок
        return f"[{title}] "
    
    def create_chunks(self, text: str, metadata: Dict[str, Any] = None) -> List[Document]:
        """Создаем чанки из текста с метаданными и заголовками"""
        if metadata is None:
            metadata = {}
        
        # Очищаем текст
        cleaned_text = self.clean_text(text)
        
        # Подготавливаем заголовок
        title_prefix = self._prepare_title(metadata)
        
        # Создаем документ LangChain
        doc = Document(page_content=cleaned_text, metadata=metadata)
        
        # Разбиваем на чанки
        chunks = self.text_splitter.split_documents([doc])
        
        # Добавляем заголовок к каждому чанку и уникальный ID
        for i, chunk in enumerate(chunks):
            # Добавляем заголовок в начало контента
            if title_prefix and not chunk.page_content.startswith(title_prefix):
                chunk.page_content = title_prefix + chunk.page_content
            
            # Добавляем метаданные
            chunk.metadata['chunk_id'] = i
            chunk.metadata['chunk_index'] = f"{metadata.get('chunk_id', 0)}.{i}"
            chunk.metadata['hash'] = self._create_hash(chunk.page_content)
        
        logger.info(f"Создано {len(chunks)} чанков из текста ({len(cleaned_text)} символов)")
        
        # Проверяем, что заголовок добавлен
        if chunks and self.include_title:
            first_chunk_preview = chunks[0].page_content[:100]
            logger.debug(f"Первый чанк (начало): {first_chunk_preview}")
        
        return chunks
    
    def _create_hash(self, text: str) -> str:
        """Создаем хэш для контента"""
        return hashlib.md5(text.encode()).hexdigest()[:8]
    
    def process_file(self, file_path: str) -> List[Document]:
        """Обрабатываем файл с текстом"""
        logger.info(f"Обрабатываю файл: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            # Разбиваем на разделы
            sections = self.extract_sections(text)
            
            all_chunks = []
            for section in sections:
                # Создаем метаданные для раздела
                metadata = {
                    'source': file_path,
                    'section_title': section['title'],
                    'section_chars': section['characters'],
                    'title': section['title']  # Добавляем заголовок раздела
                }
                
                # Создаем чанки для раздела
                chunks = self.create_chunks(section['content'], metadata)
                all_chunks.extend(chunks)
            
            logger.info(f"Всего создано {len(all_chunks)} чанков из {len(sections)} разделов")
            return all_chunks
            
        except Exception as e:
            logger.error(f"Ошибка при обработке файла {file_path}: {e}")
            return []

if __name__ == "__main__":
    # Тестируем процессор с заголовками
    import logging
    logging.basicConfig(level=logging.INFO)
    
    processor = TextProcessor(include_title=True)
    test_text = "Это тестовый текст. " * 100
    test_metadata = {
        'source': 'test',
        'title': 'Очень длинный заголовок который нужно обрезать до 30 символов',
        'short_title': 'Короткий заголовок'
    }
    chunks = processor.create_chunks(test_text, test_metadata)
    
    print(f"Создано {len(chunks)} чанков:")
    for i, chunk in enumerate(chunks[:2]):  # Показываем первые 2
        print(f"\nЧанк {i+1}:")
        print(f"  Длина: {len(chunk.page_content)} символов")
        print(f"  Контент: {chunk.page_content[:150]}...")
        print(f"  Метаданные: {chunk.metadata}")