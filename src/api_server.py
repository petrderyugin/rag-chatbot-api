
"""
FastAPI сервер для RAG QA системы
"""
import sys
import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime

# Корректный импорт config из корня
try:
    from config import config
except ImportError:
    # Если config не найден в пути, добавляем родительскую директорию
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import config

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from src.qa_system import QASystem

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Pydantic модели для валидации запросов/ответов
class QuestionRequest(BaseModel):
    """Модель запроса от пользователя"""
    session_id: str = Field(
        ...,
        description="Уникальный идентификатор сессии диалога",
        example="user_123_session_1"
    )
    question: str = Field(
        ...,
        description="Вопрос пользователя",
        example="Какие решения на основе искусственного интеллекта создаёт Neoflex?"
    )

class SourceDocument(BaseModel):
    """Модель документа-источника"""
    source: str = Field(..., description="Источник документа", example="https://neoflex.ru/services")
    snippet: str = Field(..., description="Фрагмент текста", example="Neoflex создает решения на базе ИИ...")
    title: Optional[str] = Field(None, description="Заголовок документа", example="Услуги Data Science")
    relevance: Optional[float] = Field(None, description="Релевантность документа", example=0.85)

class QuestionResponse(BaseModel):
    """Модель ответа системы"""
    answer: str = Field(
        ...,
        description="Ответ системы",
        example="Компания Neoflex разрабатывает решения на базе искусственного интеллекта..."
    )
    source_documents: list[SourceDocument] = Field(
        default_factory=list,
        description="Список документов-источников"
    )
    session_id: str = Field(..., description="Идентификатор сессии", example="user_123_session_1")
    is_about_company: Optional[bool] = Field(
        None,
        description="Относится ли вопрос к компании Neoflex",
        example=True
    )
    processing_time: Optional[float] = Field(
        None,
        description="Время обработки запроса в секундах",
        example=2.5
    )

class SystemHealth(BaseModel):
    """Статус системы"""
    status: str
    timestamp: str
    version: str = "1.0.0"
    vector_db_ready: bool
    llm_available: bool
    active_sessions: int

# Инициализация FastAPI приложения
app = FastAPI(
    title="Neoflex RAG QA API",
    description="API для вопросно-ответной системы с RAG и поддержкой свободного диалога",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальные переменные
qa_system = None
startup_time = datetime.now()

@app.on_event("startup")
def startup_event():
    """Инициализация при запуске сервера"""
    global qa_system
    logger.info("Запуск API сервера...")
    
    try:
        # Инициализируем QA систему
        qa_system = QASystem(use_local_embeddings=True)
        logger.info("✅ QA система инициализирована")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации: {e}")
        raise

@app.get("/", tags=["Система"])
def root():
    """Корневой endpoint"""
    return {
        "message": "Neoflex RAG QA API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health", response_model=SystemHealth, tags=["Система"])
def health_check():
    """Проверка состояния системы"""
    vector_db_ready = qa_system.vector_store is not None
    
    # Проверяем LLM доступность
    llm_available = False
    try:
        # Быстрая проверка - задаем простой вопрос
        test_result = qa_system.ask_question(
            question="Привет",
            session_id="health_check_session",
            classify_question=False
        )
        llm_available = True
    except Exception as e:
        logger.warning(f"LLM проверка не удалась: {e}")
    
    # Получаем количество активных сессий
    active_sessions = 0
    try:
        if hasattr(qa_system.memory, 'sessions'):
            active_sessions = len(qa_system.memory.sessions)
    except:
        pass
    
    return SystemHealth(
        status="healthy" if vector_db_ready else "degraded",
        timestamp=datetime.now().isoformat(),
        vector_db_ready=vector_db_ready,
        llm_available=llm_available,
        active_sessions=active_sessions
    )

@app.post("/ask", response_model=QuestionResponse, tags=["QA"])
def ask_question(request: QuestionRequest):
    """
    Основной endpoint для вопросов
    """
    start_time = datetime.now()
    
    try:
        logger.info(f"Запрос от сессии {request.session_id}: {request.question[:100]}...")
        
        if qa_system is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="QA система не инициализирована"
            )
        
        # Используем синхронный метод
        result = qa_system.ask_question(
            question=request.question,
            session_id=request.session_id
        )
        
        # Формируем ответ
        response = QuestionResponse(
            answer=result["answer"],
            session_id=request.session_id,
            is_about_company=result.get("is_about_company", None),
            processing_time=(datetime.now() - start_time).total_seconds(),
            source_documents=[
                SourceDocument(
                    source=doc.get("url", "N/A"),
                    snippet=doc.get("content_preview", ""),
                    title=doc.get("title", ""),
                    relevance=doc.get("score", 0.0)
                )
                for doc in result.get("sources", [])
            ]
        )
        
        logger.info(f"Ответ готов для сессии {request.session_id}, время: {response.processing_time:.2f}с")
        
        return response
        
    except Exception as e:
        logger.error(f"Ошибка при обработке вопроса: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обработке вопроса: {str(e)}"
        )

@app.get("/session/{session_id}", tags=["Сессии"])
def get_session_info(session_id: str):
    """Получить информацию о сессии"""
    if qa_system is None:
        raise HTTPException(status_code=503, detail="Система не инициализирована")
    
    info = qa_system.memory.get_session_info(session_id)
    
    if not info["exists"]:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    return {
        "session_id": session_id,
        "message_count": info["message_count"],
        "last_access": info["last_access"],
        "history_preview": info["history_preview"]
    }

@app.delete("/session/{session_id}", tags=["Сессии"])
def clear_session(session_id: str):
    """Очистить историю сессии"""
    if qa_system is None:
        raise HTTPException(status_code=503, detail="Система не инициализирована")
    
    success = qa_system.memory.clear_history(session_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    return {"message": f"История сессии {session_id} очищена", "success": True}

@app.get("/sessions", tags=["Сессии"])
def list_sessions():
    """Список активных сессий"""
    if qa_system is None:
        raise HTTPException(status_code=503, detail="Система не инициализирована")
    
    sessions = []
    for session_id, data in qa_system.memory.sessions.items():
        sessions.append({
            "session_id": session_id,
            "message_count": len(data["history"]),
            "last_access": data["last_access"].isoformat(),
            "created_at": data["history"][0]["timestamp"] if data["history"] else data["last_access"].isoformat()
        })
    
    return {
        "total_sessions": len(sessions),
        "sessions": sessions
    }

@app.get("/test", tags=["Тестирование"])
def test_endpoint():
    """Тестовый endpoint для проверки работы"""
    test_questions = [
        "Какие решения на основе ИИ создаёт Neoflex?",
        "Что такое машинное обучение?",
        "Расскажи анекдот",
        "Какие офисы есть у Neoflex?"
    ]
    
    results = []
    
    # Обрабатываем вопросы последовательно
    for question in test_questions:
        result = qa_system.ask_question(
            question=question,
            session_id="test_api_session"
        )
        results.append({
            "question": question,
            "answer_preview": result["answer"][:100] + "..." if len(result["answer"]) > 100 else result["answer"],
            "is_about_company": result.get("is_about_company", None),
            "sources_count": len(result.get("sources", []))
        })
    
    return {
        "system": "Neoflex RAG QA API",
        "status": "operational",
        "test_results": results
    }

if __name__ == "__main__":
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )