"""
QA система с LLM-классификацией вопросов и поддержкой свободного диалога
"""
import sys
import os
import logging
import json
import re
from typing import List, Dict, Any, Tuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from src.vector_store_manager import HybridSearchVectorStoreManager
from src.chat_memory import chat_memory
from langchain_core.documents import Document

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class QASystem:
    """QA система с RAG, LLM-классификацией вопросов и свободным диалогом"""
    
    def __init__(self, use_local_embeddings: bool = True):
        """
        Инициализация QA системы
        
        Args:
            use_local_embeddings: Использовать локальные эмбеддинги
        """
        logger.info("Инициализация QASystem...")
        
        # Инициализируем менеджер векторной БД
        self.vector_manager = HybridSearchVectorStoreManager(
            use_local_embeddings=use_local_embeddings
        )
        
        # Загружаем векторную базу
        self.vector_store = self.vector_manager.load_vector_store()
        if not self.vector_store:
            logger.error("Не удалось загрузить векторную базу!")
            raise RuntimeError("Векторная база не найдена. Запустите create_vector_db_from_json.py сначала.")
        
        # Используем глобальный экземпляр памяти
        self.memory = chat_memory
        
        logger.info("QASystem инициализирован")
    
    def _classify_question_with_llm(self, question: str, session_id: str) -> Dict[str, Any]:
        """
        Классификация вопроса с помощью LLM: по теме компании или общий
        
        Args:
            question: Вопрос пользователя
            session_id: ID сессии для получения истории
            
        Returns:
            Словарь с классификацией
        """
        logger.info(f"LLM-классификация вопроса: '{question[:100]}...'")
        
        # Получаем историю диалога
        history_text = self.memory.format_history_for_prompt(session_id)
        
        # Формируем промпт для классификации
        classification_prompt = f"""Ты - классификатор вопросов для чат-бота компании Neoflex.

Твоя задача - определить, относится ли вопрос пользователя к компании Neoflex или это общий вопрос.

КОМПАНИЯ NEOFLEX: Это IT-компания, которая создает решения на основе искусственного интеллекта, 
предоставляет услуги data science, занимается разработкой программного обеспечения и т.д.

К ВОПРОСАМ О КОМПАНИИ ОТНОСЯТСЯ:
- Вопросы о решениях, услугах, продуктах Neoflex
- Вопросы о клиентах, партнерах, кейсах внедрения
- Вопросы об офисах, адресах, контактах
- Вопросы о вакансиях, карьере в компании
- Вопросы об экспертизе, технологиях компании
- Вопросы, явно содержащие "Neoflex", "Неофлекс"
- Уточняющие вопросы в контексте предыдущих вопросов о компании

ОБЩИЕ ВОПРОСЫ:
- Приветствия, прощания
- Вопросы о погоде, времени
- Философские, абстрактные вопросы
- Вопросы о других компаниях/технологиях
- Общие вопросы о программировании, data science (без привязки к Neoflex)
- Вопросы, не связанные с деятельностью компании

ИСТОРИЯ ДИАЛОГА:
{history_text}

ТЕКУЩИЙ ВОПРОС: {question}

ОТВЕТЬ В ФОРМАТЕ JSON:
{{
  "is_about_company": true/false,
  "confidence": число от 0 до 1,
  "reason": "краткое объяснение решения"
}}

Важно: ответь ТОЛЬКО JSON, без других текстов."""
        
        try:
            # Вызываем LLM для классификации
            classification_result = self._call_llm(
                prompt=classification_prompt,
                temperature=0.1,  # Низкая температура для более консервативных ответов
                max_tokens=200
            )
            
            # Пытаемся распарсить JSON
            result_json = self._extract_json_from_response(classification_result)
            
            if result_json and "is_about_company" in result_json:
                is_about_company = bool(result_json["is_about_company"])
                confidence = float(result_json.get("confidence", 0.8))
                reason = result_json.get("reason", "Не указано")
                
                logger.info(f"LLM классификация: is_about_company={is_about_company}, confidence={confidence:.2f}")
                
                return {
                    "is_about_company": is_about_company,
                    "category": "llm_classification",
                    "confidence": confidence,
                    "reason": reason
                }
            else:
                logger.warning(f"LLM вернула некорректный JSON: {classification_result}")
                
        except Exception as e:
            logger.error(f"Ошибка при LLM-классификации: {e}")
        
        # Fallback: если LLM не сработала, используем простую эвристику
        return self._classify_with_heuristics(question)
    
    def _classify_with_heuristics(self, question: str) -> Dict[str, Any]:
        """
        Простая эвристическая классификация на случай ошибки LLM
        
        Args:
            question: Вопрос пользователя
            
        Returns:
            Словарь с классификацией
        """
        question_lower = question.lower()
        
        # Ключевые слова компании
        company_keywords = [
            'neoflex', 'неофлекс', 'нейрофлекс',
            'компани', 'фирм', 'организац',
            'офис', 'адрес', 'контакт',
            'услуг', 'сервис', 'решен', 'продукт',
            'клиент', 'заказчик', 'партнер',
            'ваканс', 'работ', 'карьер',
            'mlops', 'data science', 'ai', 'искусственн'
        ]
        
        # Проверяем наличие ключевых слов
        for keyword in company_keywords:
            if keyword in question_lower:
                return {
                    "is_about_company": True,
                    "category": "keyword_heuristic",
                    "confidence": 0.7,
                    "reason": f"Найдено ключевое слово: {keyword}"
                }
        
        # Проверяем явное упоминание Neoflex
        if 'neoflex' in question_lower or 'неофлекс' in question_lower:
            return {
                "is_about_company": True,
                "category": "explicit_mention",
                "confidence": 0.9,
                "reason": "Явное упоминание Neoflex"
            }
        
        # По умолчанию - общий вопрос
        return {
            "is_about_company": False,
            "category": "general_heuristic",
            "confidence": 0.6,
            "reason": "Не найдено указаний на тему компании"
        }
    
    def _extract_json_from_response(self, response: str) -> Optional[Dict]:
        """
        Извлекаем JSON из ответа LLM
        
        Args:
            response: Ответ от LLM
            
        Returns:
            Распарсенный JSON или None
        """
        try:
            # Ищем JSON в ответе (могут быть лишние символы)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Ошибка парсинга JSON: {e}")
        
        return None
    
    def _get_chunks_from_both_searches(self, query: str, 
                                       vector_k: int = 5, 
                                       bm25_k: int = 5) -> List[Tuple[Document, float]]:
        """
        Получаем чанки из обоих типов поиска и объединяем
        
        Args:
            query: Вопрос пользователя
            vector_k: Количество результатов векторного поиска
            bm25_k: Количество результатов BM25 поиска
            
        Returns:
            Список уникальных чанков с оценками
        """
        logger.info(f"Поиск чанков для запроса: '{query}'")
        
        # 1. Получаем результаты векторного поиска
        vector_results = self.vector_manager.vector_search_with_score(
            query=query, 
            k=vector_k
        )
        
        # 2. Получаем результаты BM25 поиска
        bm25_results = self.vector_manager.bm25_search(
            query=query,
            k=bm25_k
        )
        
        # 3. Объединяем и удаляем дубликаты по контенту
        all_results = {}
        
        # Добавляем векторные результаты
        for doc, score in vector_results:
            content_hash = self._get_content_hash(doc.page_content)
            similarity_score = 1 - (score / 2) if score <= 2 else 0
            all_results[content_hash] = (doc, similarity_score, 'vector')
        
        # Добавляем BM25 результаты
        for doc, score in bm25_results:
            content_hash = self._get_content_hash(doc.page_content)
            if content_hash in all_results:
                existing_doc, existing_score, source = all_results[content_hash]
                new_score = (existing_score + score) / 2
                all_results[content_hash] = (existing_doc, new_score, 'hybrid')
            else:
                all_results[content_hash] = (doc, score, 'bm25')
        
        # 4. Сортируем по оценке
        sorted_results = sorted(
            all_results.values(), 
            key=lambda x: x[1], 
            reverse=True
        )
        
        # 5. Формируем итоговый список
        final_results = [(doc, score) for doc, score, source in sorted_results]
        
        logger.info(f"Объединено {len(final_results)} уникальных чанков")
        
        return final_results
    
    def _get_content_hash(self, text: str) -> str:
        """Создаем хэш для контента"""
        import hashlib
        normalized_text = ' '.join(text.strip().lower().split())
        return hashlib.md5(normalized_text.encode()).hexdigest()[:16]
    
    def _build_prompt_for_company_question(self, question: str, 
                                          chunks: List[Tuple[Document, float]], 
                                          session_id: str) -> str:
        """
        Формируем промпт для вопросов по теме компании
        
        Args:
            question: Вопрос пользователя
            chunks: Список чанков с оценками
            session_id: ID сессии для получения истории
            
        Returns:
            Сформированный промпт
        """
        # Получаем историю диалога
        history_text = self.memory.format_history_for_prompt(session_id)
        
        # Формируем контекст из чанков
        context_parts = []
        for i, (chunk, score) in enumerate(chunks):
            chunk_text = chunk.page_content.strip()
            context_parts.append(f"[Документ {i+1}, релевантность: {score:.2f}]\n{chunk_text}\n")
        
        context = "\n".join(context_parts)
        
        # Формируем системный промпт
        system_prompt = """Ты - профессиональный ассистент компании Neoflex. 
Твоя задача - отвечать на вопросы пользователей на основе предоставленного контекста и истории диалога.

ВНИМАНИЕ - КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
1. Отвечай ТОЛЬКО на основе информации из предоставленного контекста.
2. Учитывай историю диалога для понимания контекста беседы.
3. Если в контексте НЕТ информации для ответа на вопрос, скажи: "На основе предоставленной информации не могу ответить на вопрос".
4. Не придумывай информацию, не упоминай факты не из контекста.
5. Если информация есть - ответь кратко, точно и по делу.
6. Для важных фактов укажи источники в формате [Документ X].

{history}

Контекст для ответа (информация с сайта Neoflex):
{context}

Текущий вопрос пользователя: {question}

Помни: если информации для ответа нет - говори "не могу ответить". Не выдумывай!

Ответ (отвечай как в диалоге, естественно):"""
        
        prompt = system_prompt.format(
            history=history_text,
            context=context,
            question=question
        )
        
        logger.info(f"Длина промпта (компания): {len(prompt)} символов")
        
        return prompt
    
    def _build_prompt_for_general_question(self, question: str, session_id: str) -> str:
        """
        Формируем промпт для общих вопросов
        
        Args:
            question: Вопрос пользователя
            session_id: ID сессии для получения истории
            
        Returns:
            Сформированный промпт
        """
        # Получаем историю диалога
        history_text = self.memory.format_history_for_prompt(session_id)
        
        # Формируем промпт
        system_prompt = """Ты - полезный и дружелюбный AI-ассистент. 
Ты можешь поддерживать беседу на любые темы, давать советы, отвечать на общие вопросы.
Будь вежливым, полезным и дружелюбным.

{history}

Текущий вопрос пользователя: {question}

Ответь естественно и дружелюбно, как в диалоге:"""
        
        prompt = system_prompt.format(
            history=history_text,
            question=question
        )
        
        logger.info(f"Длина промпта (общий): {len(prompt)} символов")
        
        return prompt
    
    def _call_llm(self, prompt: str, temperature: float = 0.1, max_tokens: int = 1000) -> str:
        """
        Вызов LLM через OpenRouter API
        
        Args:
            prompt: Промпт для LLM
            temperature: Температура генерации
            max_tokens: Максимальное количество токенов в ответе
            
        Returns:
            Ответ от LLM
        """
        import requests
        
        logger.info("Вызов LLM через OpenRouter...")
        
        # Проверяем API ключ
        if not config.OPENROUTER_API_KEY:
            logger.error("OPENROUTER_API_KEY не установлен!")
            return "Ошибка: API ключ не настроен"
        
        # Подготавливаем запрос
        url = f"{config.OPENROUTER_BASE_URL}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Neoflex RAG QA System"
        }
        
        data = {
            "model": config.LLM_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            answer = result['choices'][0]['message']['content'].strip()
            
            usage = result.get('usage', {})
            logger.info(f"Использовано токенов: {usage.get('total_tokens', 'N/A')}")
            
            return answer
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при вызове API: {e}")
            return f"Ошибка при обращении к модели: {str(e)}"
        except (KeyError, IndexError) as e:
            logger.error(f"Ошибка при разборе ответа API: {e}")
            return "Ошибка при обработке ответа от модели"
    
    def ask_question(self, question: str, 
                     session_id: str = "default_session",
                     vector_k: int = 5, 
                     bm25_k: int = 5,
                     classify_question: bool = True) -> Dict[str, Any]:
        """
        Основной метод для ответа на вопрос
        
        Args:
            question: Вопрос пользователя
            session_id: ID сессии для истории диалога
            vector_k: Количество результатов векторного поиска
            bm25_k: Количество результатов BM25 поиска
            classify_question: Нужно ли классифицировать вопрос
            
        Returns:
            Словарь с ответом и метаданными
        """
        logger.info(f"Обработка вопроса для сессии '{session_id}': '{question}'")
        
        # Добавляем вопрос пользователя в историю
        self.memory.add_message(session_id, "user", question)
        
        # 1. Классифицируем вопрос
        classification = None
        if classify_question:
            classification = self._classify_question_with_llm(question, session_id)
            logger.info(f"Классификация вопроса: {classification}")
        else:
            classification = {
                "is_about_company": True,  # По умолчанию считаем по теме
                "category": "forced_company",
                "confidence": 1.0,
                "reason": "Классификация отключена"
            }
        
        is_about_company = classification["is_about_company"]
        
        # 2. Получаем чанки только если вопрос по теме компании
        chunks_with_scores = []
        if is_about_company:
            chunks_with_scores = self._get_chunks_from_both_searches(
                question, vector_k, bm25_k
            )
        
        # 3. Формируем промпт в зависимости от классификации
        if is_about_company:
            # Для вопросов по теме компании
            if not chunks_with_scores:
                logger.warning("Вопрос по теме компании, но не найдено чанков")
                answer = "На основе предоставленной информации не могу ответить на вопрос"
            else:
                prompt = self._build_prompt_for_company_question(
                    question, chunks_with_scores, session_id
                )
                answer = self._call_llm(prompt, temperature=0.1, max_tokens=1000)
        else:
            # Для общих вопросов
            prompt = self._build_prompt_for_general_question(question, session_id)
            answer = self._call_llm(prompt, temperature=0.7, max_tokens=800)  # Более творческий ответ
        
        # 4. Добавляем ответ ассистента в историю
        self.memory.add_message(session_id, "assistant", answer)
        
        # 5. Анализируем ответ на предмет "не знаю"
        not_found_phrases = [
            "не могу ответить",
            "нет информации",
            "информации нет",
            "не могу найти",
            "не предоставлено",
            "не знаю",
            "не удалось найти"
        ]
        
        knows_answer = True
        for phrase in not_found_phrases:
            if phrase in answer.lower():
                knows_answer = False
                break
        
        # 6. Подготавливаем источники (только для вопросов по теме)
        sources = []
        if is_about_company and knows_answer and chunks_with_scores:
            for i, (chunk, score) in enumerate(chunks_with_scores[:3]):
                if score > 0.3:
                    source_info = {
                        "content_preview": chunk.page_content[:200] + "..." if len(chunk.page_content) > 200 else chunk.page_content,
                        "score": float(score),
                        "url": chunk.metadata.get('url', 'N/A'),
                        "title": chunk.metadata.get('original_title', chunk.metadata.get('title', 'N/A'))
                    }
                    sources.append(source_info)
        
        # 7. Формируем результат
        result = {
            "answer": answer,
            "sources": sources,
            "used_chunks": len(sources),
            "total_chunks_found": len(chunks_with_scores),
            "question": question,
            "session_id": session_id,
            "knows_answer": knows_answer,
            "history_length": len(self.memory.get_history(session_id)),
            "is_about_company": is_about_company,
            "classification": classification if classify_question else None
        }
        
        logger.info(f"Ответ готов. Тип: {'компания' if is_about_company else 'общий'}, "
                   f"источников: {len(sources)}")
        
        return result
    
    def get_session_history(self, session_id: str) -> List[Dict]:
        """Получаем полную историю сессии"""
        return self.memory.get_history(session_id)
    
    def clear_session_history(self, session_id: str) -> bool:
        """Очищаем историю сессии"""
        return self.memory.clear_history(session_id)


def test_llm_classification():
    """Тестирование LLM классификации"""
    import logging
    logging.basicConfig(level=logging.INFO)
    
    logger.info("=" * 60)
    logger.info("ТЕСТИРОВАНИЕ LLM КЛАССИФИКАЦИИ ВОПРОСОВ")
    logger.info("=" * 60)
    
    try:
        # Инициализируем систему
        qa_system = QASystem(use_local_embeddings=True)
        
        # Тестовые вопросы
        test_questions = [
            ("Какие решения на основе ИИ создаёт Neoflex?", True),
            ("Привет! Как дела?", False),
            ("Что такое машинное обучение?", False),
            ("Какие офисы есть у Neoflex?", True),
            ("Расскажи анекдот", False),
            ("Кто является клиентами Neoflex?", True),
            ("Что вы думаете о будущем искусственного интеллекта?", False),
            ("Какие вакансии есть в Neoflex?", True),
            ("Как погода?", False),
            ("Какие технологии использует Neoflex в своих проектах?", True)
        ]
        
        for i, (question, expected_type) in enumerate(test_questions, 1):
            print(f"\n{'='*60}")
            print(f"Тест {i}: '{question}'")
            print(f"Ожидаемый тип: {'компания' if expected_type else 'общий'}")
            print(f"{'='*60}")
            
            # Создаем новую сессию для каждого вопроса
            session_id = f"test_session_{i}"
            
            # Классифицируем вопрос
            classification = qa_system._classify_question_with_llm(question, session_id)
            
            actual_type = classification["is_about_company"]
            print(f"Результат классификации:")
            print(f"  Тип: {'компания' if actual_type else 'общий'}")
            print(f"  Категория: {classification['category']}")
            print(f"  Уверенность: {classification['confidence']:.2f}")
            print(f"  Причина: {classification['reason']}")
            
            if actual_type != expected_type:
                print(f"  ⚠️  Несоответствие ожидаемого типа!")
        
        print(f"\n{'='*60}")
        print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
        print(f"{'='*60}")
        
    except Exception as e:
        logger.error(f"Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_llm_classification()