# RAG QA System

Вопросно-ответная система с RAG (Retrieval-Augmented Generation) для Компании.

## Особенности

- **RAG-система**: Извлекает информацию с сайта Компании и генерирует точные ответы
- **Свободный диалог**: Поддерживает общение на любые темы
- **Гибридный поиск**: Комбинация векторного и BM25 поиска
- **История диалогов**: Сохраняет контекст беседы
- **LLM-классификация**: Автоматически определяет тип вопроса

## Архитектура

1. **Парсинг данных**: `crawler_to_csv.py` → `convert_to_json.py`
2. **Обработка текста**: `text_processor.py`
3. **Векторная БД**: `vector_store_manager.py`
4. **QA система**: `qa_system.py` с LLM-классификацией
5. **API сервер**: FastAPI (`api_server.py`)
6. **Память диалогов**: `chat_memory.py`

## Быстрый старт

### Локальная установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/petrderyugin/rag-chatbot-api
cd rag-chatbot-api
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл .env:
```env
OPENROUTER_API_KEY="ваш_ключ_от_openrouter"
```

4. Векторная база данных уже включена в репозиторий. Если вы хотите пересоздать её, выполните:
```bash
python src/create_vector_db_from_json.py
```

5. Запустите сервер:
```bash
python run_server_simple.py
```

### Docker запуск

1. Создайте файл .env с ключом API (см. выше)

2. Запустите Docker Compose:
```bash
docker-compose up -d
```

3. Сервер будет доступен: http://localhost:8000

## Использование API

### Основные endpoints:

* GET / - Информация о системе
* GET /health - Проверка состояния
* POST /ask - Задать вопрос
* GET /session/{session_id} - Получить историю сессии
* DELETE /session/{session_id} - Очистить историю сессии

### Пример запроса:

```bash
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_session",
    "question": "Какие решения на основе ИИ создаёт компания?"
  }'
 ```

### Пример ответа:

```json
{
  "answer": "Компания создает решения на основе...",
  "source_documents": [...],
  "session_id": "test_session",
  "is_about_company": true
}
```

## Структура проекта

```text
rag-chatbot-api/
├── src/
│   ├── api_server.py           # FastAPI сервер
│   ├── qa_system.py           # Основная QA логика
│   ├── vector_store_manager.py # Гибридный поиск
│   ├── text_processor.py       # Обработка текста
│   ├── chat_memory.py         # Управление диалогами
│   ├── create_vector_db_from_json.py
│   ├── convert_to_json.py
│   └── crawler_to_csv.py
├── data/                      # Данные и векторная БД
│   ├── crawled_data.json      # Исходные данные
│   ├── crawled_data.csv       # CSV версия данных
│   └── vector_db/             # Векторная база данных (предсозданная)
├── docker/                    # Docker конфигурации
├── .env.example              # Пример переменных окружения
├── config.py                 # Конфигурация
├── run_server_simple.py      # Скрипт запуска
├── requirements.txt          # Зависимости
├── Dockerfile
├── docker-compose.yaml
└── README.md
```

## Конфигурация

Ключевые параметры в config.py:
* CHUNK_SIZE: Размер чанков (по умолчанию 1000)
* CHUNK_OVERLAP: Перекрытие между чанками (по умолчанию 200)
* INCLUDE_TITLES: Включать ли заголовки страниц в начало чанка (по умолчанию - Да)
* MAX_TITLE_LENGTH: Максимальная длина заголовка в чанке (по умолчанию 100)
* LLM_MODEL: Модель для генерации (можно менять)