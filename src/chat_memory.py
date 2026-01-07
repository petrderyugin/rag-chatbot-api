"""
Модуль для управления диалоговой памятью с поддержкой session_id
"""
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ChatMemory:
    """Класс для управления диалоговой памятью с TTL (время жизни сессий)"""
    
    def __init__(self, ttl_hours: int = 24, max_history_length: int = 10):
        """
        Инициализация менеджера памяти
        
        Args:
            ttl_hours: Время жизни сессии в часах
            max_history_length: Максимальное количество сообщений в истории
        """
        self.ttl_hours = ttl_hours
        self.max_history_length = max_history_length
        
        # Хранилище в памяти: session_id -> {"history": [], "last_access": timestamp}
        self.sessions: Dict[str, Dict] = {}
        
        # Если хотим сохранять между запусками - используем файл
        self.storage_file = "data/chat_sessions.json"
        
        # Загружаем сохраненные сессии
        self._load_sessions()
    
    def _load_sessions(self):
        """Загружаем сессии из файла (если есть)"""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    saved_data = json.load(f)
                
                # Восстанавливаем сессии, фильтруя просроченные
                now = datetime.now()
                for session_id, session_data in saved_data.items():
                    last_access = datetime.fromisoformat(session_data["last_access"])
                    if now - last_access < timedelta(hours=self.ttl_hours):
                        self.sessions[session_id] = {
                            "history": session_data["history"],
                            "last_access": last_access
                        }
                
                logger.info(f"Загружено {len(self.sessions)} активных сессий из файла")
                
            except Exception as e:
                logger.error(f"Ошибка при загрузке сессий: {e}")
    
    def _save_sessions(self):
        """Сохраняем сессии в файл"""
        try:
            # Создаем директорию, если нет
            os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
            
            # Преобразуем datetime в строку для сериализации
            serializable_sessions = {}
            for session_id, session_data in self.sessions.items():
                serializable_sessions[session_id] = {
                    "history": session_data["history"],
                    "last_access": session_data["last_access"].isoformat()
                }
            
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_sessions, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Сохранено {len(self.sessions)} сессий")
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении сессий: {e}")
    
    def _cleanup_old_sessions(self):
        """Удаляем просроченные сессии"""
        now = datetime.now()
        to_delete = []
        
        for session_id, session_data in self.sessions.items():
            if now - session_data["last_access"] > timedelta(hours=self.ttl_hours):
                to_delete.append(session_id)
        
        for session_id in to_delete:
            del self.sessions[session_id]
        
        if to_delete:
            logger.info(f"Удалено {len(to_delete)} просроченных сессий")
            self._save_sessions()
    
    def add_message(self, session_id: str, role: str, content: str) -> None:
        """
        Добавляем сообщение в историю сессии
        
        Args:
            session_id: ID сессии
            role: 'user' или 'assistant'
            content: Текст сообщения
        """
        # Очищаем старые сессии перед добавлением
        self._cleanup_old_sessions()
        
        # Создаем новую сессию, если нужно
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "history": [],
                "last_access": datetime.now()
            }
            logger.info(f"Создана новая сессия: {session_id}")
        
        # Добавляем сообщение в историю
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        self.sessions[session_id]["history"].append(message)
        
        # Обновляем время последнего доступа
        self.sessions[session_id]["last_access"] = datetime.now()
        
        # Ограничиваем длину истории
        if len(self.sessions[session_id]["history"]) > self.max_history_length:
            # Удаляем самые старые сообщения, но сохраняем хотя бы последние 2 пары Q/A
            keep_count = min(self.max_history_length, 4)  # 2 пары
            self.sessions[session_id]["history"] = self.sessions[session_id]["history"][-keep_count:]
        
        # Сохраняем изменения
        self._save_sessions()
        
        logger.debug(f"Добавлено сообщение в сессию {session_id}: {role} ({len(content)} chars)")
    
    def get_history(self, session_id: str, max_messages: Optional[int] = None) -> List[Dict]:
        """
        Получаем историю сообщений для сессии
        
        Args:
            session_id: ID сессии
            max_messages: Максимальное количество сообщений для возврата
            
        Returns:
            Список сообщений в формате {"role": ..., "content": ...}
        """
        if session_id not in self.sessions:
            return []
        
        history = self.sessions[session_id]["history"]
        
        # Обновляем время доступа
        self.sessions[session_id]["last_access"] = datetime.now()
        
        if max_messages and len(history) > max_messages:
            return history[-max_messages:]
        
        return history
    
    def clear_history(self, session_id: str) -> bool:
        """
        Очищаем историю сессии
        
        Args:
            session_id: ID сессии
            
        Returns:
            True если сессия найдена и очищена
        """
        if session_id in self.sessions:
            self.sessions[session_id]["history"] = []
            self._save_sessions()
            logger.info(f"История сессии {session_id} очищена")
            return True
        return False
    
    def format_history_for_prompt(self, session_id: str) -> str:
        """
        Форматируем историю для включения в промпт
        
        Args:
            session_id: ID сессии
            
        Returns:
            Отформатированная строка с историей диалога
        """
        history = self.get_history(session_id)
        
        if not history:
            return "История диалога: (диалог только начался)"
        
        formatted_lines = ["История диалога:"]
        
        for i, msg in enumerate(history, 1):
            if msg["role"] == "user":
                formatted_lines.append(f"Пользователь: {msg['content']}")
            else:
                formatted_lines.append(f"Ассистент: {msg['content']}")
        
        return "\n".join(formatted_lines)
    
    def get_session_info(self, session_id: str) -> Dict:
        """
        Получаем информацию о сессии
        
        Args:
            session_id: ID сессии
            
        Returns:
            Словарь с информацией о сессии
        """
        if session_id not in self.sessions:
            return {"exists": False}
        
        session_data = self.sessions[session_id]
        return {
            "exists": True,
            "message_count": len(session_data["history"]),
            "last_access": session_data["last_access"].isoformat(),
            "history_preview": [
                {"role": msg["role"], "content_preview": msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]}
                for msg in session_data["history"][-3:]  # Последние 3 сообщения
            ]
        }


# Глобальный экземпляр для использования во всем приложении
chat_memory = ChatMemory()


if __name__ == "__main__":
    # Тестирование класса памяти
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    memory = ChatMemory()
    
    # Тест 1: Добавление сообщений
    memory.add_message("test_session_1", "user", "Привет!")
    memory.add_message("test_session_1", "assistant", "Здравствуйте! Чем могу помочь?")
    memory.add_message("test_session_1", "user", "Какие офисы есть у Neoflex?")
    
    # Тест 2: Получение истории
    history = memory.get_history("test_session_1")
    print(f"История сообщений: {len(history)}")
    for msg in history:
        print(f"  {msg['role']}: {msg['content'][:50]}...")
    
    # Тест 3: Форматирование для промпта
    formatted = memory.format_history_for_prompt("test_session_1")
    print("\nФорматированная история:")
    print(formatted)
    
    # Тест 4: Информация о сессии
    info = memory.get_session_info("test_session_1")
    print(f"\nИнформация о сессии: {info}")
    
    # Тест 5: Очистка истории
    memory.clear_history("test_session_1")
    print(f"После очистки: {len(memory.get_history('test_session_1'))} сообщений")