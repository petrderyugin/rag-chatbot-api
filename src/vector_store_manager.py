import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import hashlib
from typing import List, Optional, Tuple
import logging
from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from rank_bm25 import BM25Okapi
import nltk
from nltk.tokenize import word_tokenize
import string

from config import config

logger = logging.getLogger(__name__)

class HybridSearchVectorStoreManager:
    """Менеджер векторной базы данных с гибридным поиском"""
    
    def __init__(self, use_local_embeddings: bool = False):
        self.use_local_embeddings = use_local_embeddings
        self.vector_store = None
        self.embeddings = None
        self.bm25_index = None
        self.all_documents = []  # Все документы для BM25
        self.all_documents_content = []  # Токенизированный контент для BM25
        
        # Инициализируем эмбеддинги
        self._init_embeddings()
        
        # Загружаем стоп-слова для русского языка
        self._load_stopwords()
    
    def _init_embeddings(self):
        """Инициализируем модель эмбеддингов"""
        if self.use_local_embeddings:
            logger.info("Использую локальные эмбеддинги (HuggingFace)")
            self.embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
                #model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                #model_name="ai-forever/FRIDA",
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )
        else:
            logger.info("Использую облачные эмбеддинги (OpenRouter)")
            if not config.OPENROUTER_API_KEY:
                raise ValueError("OPENROUTER_API_KEY не установлен!")
            
            self.embeddings = OpenAIEmbeddings(
                model=config.EMBEDDING_MODEL,
                openai_api_key=config.OPENROUTER_API_KEY,
                openai_api_base=config.OPENROUTER_BASE_URL
            )
    
    def _load_stopwords(self):
        """Загружаем стоп-слова для русского языка"""
        try:
            nltk.data.find('corpora/stopwords')
        except LookupError:
            nltk.download('stopwords')
        
        from nltk.corpus import stopwords
        self.russian_stopwords = set(stopwords.words('russian'))
    
    def _preprocess_text(self, text: str) -> List[str]:
        """Препроцессинг текста для BM25: токенизация, удаление стоп-слов, нормализация"""
        # Приводим к нижнему регистру
        text = text.lower()
        
        # Удаляем пунктуацию, но сохраняем квадратные скобки для заголовков
        # Сначала извлекаем заголовки из скобок
        import re
        # Находим заголовки в формате [Заголовок] текст
        title_match = re.match(r'^\[([^\]]+)\]\s*(.*)', text)
        
        if title_match:
            title = title_match.group(1)  # Заголовок
            main_text = title_match.group(2)  # Основной текст
            # Обрабатываем заголовок и текст отдельно
            all_text = title + " " + main_text
        else:
            all_text = text
        
        # Удаляем пунктуацию (кроме дефиса для составных слов)
        all_text = all_text.translate(str.maketrans('', '', string.punctuation.replace('-', '')))
        
        # Токенизация
        try:
            tokens = word_tokenize(all_text, language='russian')
        except:
            # Простой сплит на случай ошибки
            tokens = all_text.split()
        
        # Удаляем стоп-слова и короткие токены, но оставляем слова из заголовка
        tokens = [token for token in tokens 
                 if token not in self.russian_stopwords 
                 and len(token) > 2 
                 and token.isalpha()]
        
        return tokens
    
    def _create_document_hash(self, document: Document) -> str:
        """Создаем хэш документа, учитывающий только контент"""
        return self._create_content_hash(document.page_content)
    
    def _create_content_hash(self, text: str) -> str:
        """Создаем хэш только для контента (игнорируем метаданные)"""
        # Нормализуем текст: убираем лишние пробелы, приводим к нижнему регистру
        normalized_text = ' '.join(text.strip().lower().split())
        return hashlib.md5(normalized_text.encode()).hexdigest()[:16]
    
    def create_vector_store(self, documents: List[Document], persist: bool = True):
        """Создаем векторное хранилище из документов"""
        logger.info(f"Создаю векторное хранилище из {len(documents)} документов...")
        
        try:
            # Создаем векторное хранилище
            self.vector_store = Chroma.from_documents(
                documents=documents,
                embedding=self.embeddings,
                persist_directory=config.VECTOR_DB_PATH if persist else None,
                collection_metadata={"hnsw:space": "cosine"}
            )
            
            # Сохраняем документы для BM25
            self._build_bm25_index(documents)
            
            if persist:
                self.vector_store.persist()
                logger.info(f"Векторная база сохранена в {config.VECTOR_DB_PATH}")
            
            logger.info(f"Векторная база создана. Коллекция: {self.vector_store._collection.name}")
            logger.info(f"BM25 индекс создан. Документов в индексе: {len(self.all_documents)}")
            
            return self.vector_store
            
        except Exception as e:
            logger.error(f"Ошибка при создании векторной базы: {e}")
            raise
    
    def _build_bm25_index(self, documents: List[Document]):
        """Строим BM25 индекс из документов с удалением дубликатов по контенту"""
        logger.info("Построение BM25 индекса...")
        
        self.all_documents = []
        self.all_documents_content = []
        seen_content = set()  # Храним хэши контента
        
        for doc in documents:
            # Создаем уникальный хэш для контента
            content_hash = self._create_content_hash(doc.page_content)
            
            # Пропускаем дубликаты по контенту
            if content_hash in seen_content:
                continue
            
            seen_content.add(content_hash)
            self.all_documents.append(doc)
            
            # Препроцессинг текста для BM25
            tokens = self._preprocess_text(doc.page_content)
            self.all_documents_content.append(tokens)
        
        # Создаем BM25 индекс
        if self.all_documents_content:
            self.bm25_index = BM25Okapi(self.all_documents_content)
            logger.info(f"BM25 индекс создан для {len(self.all_documents)} уникальных документов")
        else:
            logger.warning("Нет документов для построения BM25 индекса")
    
    def load_vector_store(self):
        """Загружаем существующую векторную базу"""
        if not os.path.exists(config.VECTOR_DB_PATH):
            logger.warning(f"Векторная база не найдена по пути: {config.VECTOR_DB_PATH}")
            return None
        
        try:
            logger.info(f"Загружаю векторную базу из {config.VECTOR_DB_PATH}")
            self.vector_store = Chroma(
                persist_directory=config.VECTOR_DB_PATH,
                embedding_function=self.embeddings
            )
            
            # Загружаем все документы из векторной базы для BM25
            self._load_documents_for_bm25()
            
            count = self.vector_store._collection.count()
            logger.info(f"Векторная база загружена. Документов: {count}")
            logger.info(f"BM25 индекс загружен. Документов в индексе: {len(self.all_documents)}")
            
            return self.vector_store
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке векторной базы: {e}")
            return None
    
    def _load_documents_for_bm25(self):
        """Загружаем документы из векторной базы для BM25 индекса"""
        if not self.vector_store:
            return
        
        try:
            # Получаем все документы из коллекции
            collection = self.vector_store._collection
            results = collection.get(include=['documents', 'metadatas'])
            
            documents = []
            seen_hashes = set()
            
            for i, (content, metadata) in enumerate(zip(results['documents'], results['metadatas'])):
                doc = Document(page_content=content, metadata=metadata)
                doc_hash = self._create_document_hash(doc)
                
                # Пропускаем дубликаты
                if doc_hash in seen_hashes:
                    continue
                
                seen_hashes.add(doc_hash)
                documents.append(doc)
            
            # Строим BM25 индекс
            self._build_bm25_index(documents)
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке документов для BM25: {e}")
    
    def vector_search_with_score(self, query: str, k: int = 10) -> List[Tuple[Document, float]]:
        """Векторный поиск с удалением дубликатов по контенту"""
        if not self.vector_store:
            logger.error("Векторная база не инициализирована")
            return []
        
        try:
            # Ищем больше кандидатов, чем нужно
            initial_k = min(k * 5, 100)
            results = self.vector_store.similarity_search_with_score(
                query=query,
                k=initial_k
            )
            
            # Удаляем дубликаты по контенту
            unique_results = []
            seen_content = set()  # Храним хэши контента
            
            for doc, distance in results:
                content_hash = self._create_content_hash(doc.page_content)
                
                if content_hash in seen_content:
                    continue
                
                seen_content.add(content_hash)
                unique_results.append((doc, distance))
                
                # Останавливаемся, когда набрали k уникальных
                if len(unique_results) >= k:
                    break
            
            return unique_results[:k]
            
        except Exception as e:
            logger.error(f"Ошибка при векторном поиске: {e}")
            return []
    
    def bm25_search(self, query: str, k: int = 10) -> List[Tuple[Document, float]]:
        """BM25 поиск с удалением дубликатов по контенту"""
        if not self.bm25_index or not self.all_documents:
            logger.error("BM25 индекс не инициализирован")
            return []
        
        try:
            # Препроцессинг запроса
            query_tokens = self._preprocess_text(query)
            
            if not query_tokens:
                return []
            
            # Получаем оценки BM25
            scores = self.bm25_index.get_scores(query_tokens)
            
            # Сортируем документы по убыванию оценки
            scored_docs = list(zip(self.all_documents, scores))
            scored_docs.sort(key=lambda x: x[1], reverse=True)
            
            # Удаляем дубликаты по контенту
            unique_results = []
            seen_content = set()
            
            for doc, score in scored_docs:
                content_hash = self._create_content_hash(doc.page_content)
                
                if content_hash in seen_content:
                    continue
                
                seen_content.add(content_hash)
                unique_results.append((doc, score))
                
                if len(unique_results) >= k:
                    break
            
            return unique_results[:k]
            
        except Exception as e:
            logger.error(f"Ошибка при BM25 поиске: {e}")
            return []

    def hybrid_search(self, query: str, k: int = 4, 
                     vector_k: int = 10, bm25_k: int = 10,
                     vector_weight: float = 0.6, bm25_weight: float = 0.4) -> List[Tuple[Document, float]]:
        """Гибридный поиск: комбинация векторного и BM25 поиска"""
        logger.info(f"Гибридный поиск: '{query}'")
        
        # Выполняем оба поиска
        vector_results = self.vector_search_with_score(query, k=vector_k)
        bm25_results = self.bm25_search(query, k=bm25_k)
        
        # Нормализуем оценки
        def normalize_scores(results, is_distance=True):
            """Нормализуем оценки в диапазон [0, 1]"""
            if not results:
                return []
            
            if is_distance:
                # Для векторного поиска: преобразуем расстояние в схожесть
                normalized = [(doc, 1 - (distance / 2)) for doc, distance in results]
            else:
                # Для BM25: нормализуем к [0, 1]
                scores = [score for _, score in results]
                max_score = max(scores) if scores else 1
                if max_score > 0:
                    normalized = [(doc, score / max_score) for doc, score in results]
                else:
                    normalized = [(doc, 0.0) for doc, score in results]
            
            return normalized
        
        # Нормализуем результаты
        norm_vector = normalize_scores(vector_results, is_distance=True)
        norm_bm25 = normalize_scores(bm25_results, is_distance=False)
        
        # Объединяем результаты по хэшу контента
        all_results = {}
        
        # Добавляем векторные результаты
        for doc, score in norm_vector:
            content_hash = self._create_content_hash(doc.page_content)
            weighted_score = score * vector_weight
            all_results[content_hash] = (doc, weighted_score, 'vector')
        
        # Добавляем BM25 результаты
        for doc, score in norm_bm25:
            content_hash = self._create_content_hash(doc.page_content)
            
            if content_hash in all_results:
                # Обновляем оценку, если документ уже есть
                existing_doc, existing_score, source = all_results[content_hash]
                new_score = existing_score + (score * bm25_weight)
                all_results[content_hash] = (existing_doc, new_score, 'hybrid')
            else:
                weighted_score = score * bm25_weight
                all_results[content_hash] = (doc, weighted_score, 'bm25')
        
        # Сортируем по комбинированной оценке
        sorted_results = sorted(all_results.values(), key=lambda x: x[1], reverse=True)
        
        # Возвращаем топ-k результатов
        final_results = [(doc, score) for doc, score, source in sorted_results[:k]]
        
        logger.info(f"Найдено результатов: вектор={len(vector_results)}, BM25={len(bm25_results)}, уникальные={len(all_results)}")
        
        return final_results
    
    def delete_vector_store(self):
        """Удаляем векторную базу"""
        try:
            import shutil
            if os.path.exists(config.VECTOR_DB_PATH):
                shutil.rmtree(config.VECTOR_DB_PATH)
                logger.info(f"Векторная база удалена: {config.VECTOR_DB_PATH}")
                self.vector_store = None
                self.bm25_index = None
                self.all_documents = []
                self.all_documents_content = []
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка при удалении векторной базы: {e}")
            return False

    def search_similar(self, query: str, k: int = 4, filter_dict: Optional[dict] = None):
        """Совместимый метод: поиск похожих документов (без оценок)"""
        results = self.hybrid_search(query, k=k)
        return [doc for doc, _ in results]
    
    def search_with_score(self, query: str, k: int = 4):
        """Совместимый метод: поиск с оценкой схожести"""
        results = self.hybrid_search(query, k=k)
        # Преобразуем оценку в "расстояние" для совместимости (1 - score)
        return [(doc, 1 - score) for doc, score in results]

    def get_collection_info(self) -> dict:
        """Получаем информацию о коллекции (для обратной совместимости)"""
        if not self.vector_store:
            return {"error": "Векторная база не инициализирована"}
        
        try:
            collection = self.vector_store._collection
            count = collection.count()
            
            # Пробуем получить образец документов
            sample = collection.get(limit=1)
            
            info = {
                "collection_name": collection.name,
                "document_count": count,
                "embedding_dimension": len(sample['embeddings'][0]) if sample['embeddings'] else "unknown",
                "metadata_fields": list(sample['metadatas'][0].keys()) if sample['metadatas'] else [],
                "bm25_documents": len(self.all_documents),
                "search_type": "hybrid"
            }
            
            return info
            
        except Exception as e:
            logger.error(f"Ошибка при получении информации: {e}")
            return {"error": str(e)}