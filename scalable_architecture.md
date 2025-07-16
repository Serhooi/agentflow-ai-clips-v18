# Масштабируемая архитектура для 100+ пользователей

## Архитектура с очередью задач

### Компоненты:
1. **FastAPI** - API сервер (легкий, только прием запросов)
2. **Redis** - очередь задач и кеш
3. **Celery Workers** - обработка видео (несколько инстансов)
4. **PostgreSQL** - база данных задач
5. **S3/Supabase** - хранение файлов

### Схема:
```
Пользователь → FastAPI → Redis Queue → Celery Worker → S3 Storage
                ↓
            PostgreSQL (статусы задач)
```

### Преимущества:
- Горизонтальное масштабирование (добавляем воркеры)
- Устойчивость к сбоям
- Мониторинг очереди
- Балансировка нагрузки

## Код изменений:

### 1. Новые зависимости (requirements.txt):
```
celery[redis]==5.3.4
redis==5.0.1
psycopg2-binary==2.9.9
sqlalchemy==2.0.23
```

### 2. Celery конфигурация (celery_app.py):
```python
from celery import Celery
import os

# Celery приложение
celery_app = Celery(
    "video_processor",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    include=["tasks"]
)

# Конфигурация
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_concurrency=2,  # 2 задачи на воркер
    worker_max_memory_per_child=400000,  # 400MB лимит на задачу
)
```

### 3. Задачи Celery (tasks.py):
```python
from celery_app import celery_app
import subprocess
import os
from openai import OpenAI

@celery_app.task(bind=True)
def process_video_task(self, video_id: str, video_path: str):
    """Обработка видео в фоне"""
    try:
        # Обновляем статус
        self.update_state(state="PROGRESS", meta={"progress": 10})
        
        # Извлекаем аудио
        audio_path = extract_audio_optimized(video_path)
        self.update_state(state="PROGRESS", meta={"progress": 30})
        
        # Транскрипция
        transcript = transcribe_audio(audio_path)
        self.update_state(state="PROGRESS", meta={"progress": 70})
        
        # Анализ с ChatGPT
        highlights = analyze_with_chatgpt(transcript)
        self.update_state(state="PROGRESS", meta={"progress": 90})
        
        # Очистка временных файлов
        cleanup_temp_files([audio_path])
        
        return {
            "video_id": video_id,
            "highlights": highlights,
            "transcript": transcript,
            "status": "completed"
        }
        
    except Exception as e:
        self.update_state(state="FAILURE", meta={"error": str(e)})
        raise
```

### 4. Упрощенный FastAPI (main.py):
```python
from fastapi import FastAPI, UploadFile
from celery.result import AsyncResult
from tasks import process_video_task
import uuid

app = FastAPI()

@app.post("/api/videos/upload")
async def upload_video(file: UploadFile):
    """Загрузка и постановка в очередь"""
    video_id = str(uuid.uuid4())
    
    # Сохраняем в S3/Supabase
    file_url = await upload_to_storage(file, video_id)
    
    # Ставим задачу в очередь
    task = process_video_task.delay(video_id, file_url)
    
    return {
        "video_id": video_id,
        "task_id": task.id,
        "status": "queued"
    }

@app.get("/api/videos/{task_id}/status")
async def get_task_status(task_id: str):
    """Статус задачи"""
    result = AsyncResult(task_id, app=celery_app)
    
    if result.state == "PENDING":
        return {"status": "queued", "progress": 0}
    elif result.state == "PROGRESS":
        return {"status": "processing", "progress": result.info.get("progress", 0)}
    elif result.state == "SUCCESS":
        return {"status": "completed", "result": result.result}
    else:
        return {"status": "failed", "error": str(result.info)}
```

## Деплой архитектуры:

### Docker Compose:
```yaml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: video_app
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
  
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
      - DATABASE_URL=postgresql://user:password@postgres/video_app
    depends_on:
      - redis
      - postgres
  
  worker:
    build: .
    command: celery -A celery_app worker --loglevel=info --concurrency=2
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
    deploy:
      replicas: 3  # 3 воркера = 6 одновременных задач
```

### Render.com деплой:
1. **Web Service** - FastAPI (512MB RAM)
2. **Background Workers** - Celery (по 512MB каждый)
3. **Redis** - внешний сервис (Redis Cloud)
4. **PostgreSQL** - Render PostgreSQL

## Масштабирование:

### Для 100 пользователей:
- **API сервер:** 1 инстанс (512MB)
- **Celery воркеры:** 10-15 инстансов (по 512MB)
- **Redis:** 1GB RAM
- **PostgreSQL:** 1GB RAM
- **Общая стоимость:** ~$50-70/месяц на Render

### Мониторинг:
```python
@app.get("/api/system/queue-stats")
async def get_queue_stats():
    """Статистика очереди"""
    inspect = celery_app.control.inspect()
    
    return {
        "active_tasks": len(inspect.active() or {}),
        "scheduled_tasks": len(inspect.scheduled() or {}),
        "workers_online": len(inspect.ping() or {}),
        "queue_length": get_queue_length()  # Из Redis
    }
```

---

## Вариант 2: Микросервисная архитектура

### Разделение на сервисы:

#### 1. **API Gateway** (FastAPI)
- Прием запросов
- Аутентификация
- Роутинг запросов

#### 2. **Upload Service** 
- Загрузка файлов в S3
- Валидация видео
- Генерация превью

#### 3. **Transcription Service**
- Извлечение аудио
- Whisper транскрипция
- Кеширование результатов

#### 4. **Analysis Service**
- ChatGPT анализ
- Поиск хайлайтов
- Генерация метаданных

#### 5. **Video Processing Service**
- FFmpeg обработка
- Нарезка клипов
- Оптимизация форматов

### Схема:
```
API Gateway → Upload Service → S3
     ↓
Message Queue (RabbitMQ/SQS)
     ↓
Transcription → Analysis → Video Processing
     ↓              ↓            ↓
   Cache         Database    S3 Storage
```

### Преимущества:
- Независимое масштабирование каждого сервиса
- Отказоустойчивость
- Технологическое разнообразие
- Легкое тестирование

---

## Вариант 3: Serverless архитектура

### AWS Lambda функции:
1. **upload-handler** - загрузка файлов
2. **transcribe-handler** - транскрипция
3. **analyze-handler** - анализ с ChatGPT
4. **process-handler** - обработка видео

### Схема:
```
API Gateway → Lambda Functions → S3 + DynamoDB
                ↓
            SQS Queues (для координации)
```

### Преимущества:
- Автоматическое масштабирование
- Оплата только за использование
- Нет управления серверами
- Высокая доступность

### Недостатки:
- Лимиты времени выполнения (15 минут)
- Холодный старт
- Сложность отладки

---

## Рекомендация для твоего случая:

### Для начала (до 50 пользователей):
**Celery + Redis** - простое и эффективное решение

### Для роста (50-500 пользователей):
**Микросервисы** - больше контроля и гибкости

### Для масштаба (500+ пользователей):
**Serverless** - минимальные операционные затраты

## Быстрое решение для текущей ситуации:

### Минимальные изменения в текущем коде: