# AgentFlow AI Clips v18.6.0 - Упрощенная архитектура без Remotion
import os
import json
import uuid
import asyncio
import logging
import subprocess
import tempfile
from datetime import datetime
from typing import Dict, List, Optional, Any
import psutil
import shutil

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
import openai
from openai import OpenAI

# Настройка логирования (ПЕРВЫМ ДЕЛОМ!)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("app")

# Supabase Storage интеграция (опционально)
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("Supabase не установлен")

# Redis интеграция (опционально)
try:
    import redis
    redis_client = redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True
    )
    # Проверяем подключение
    redis_client.ping()
    REDIS_AVAILABLE = True
    logger.info("✅ Redis подключен")
except Exception as e:
    REDIS_AVAILABLE = False
    redis_client = None
    logger.warning(f"⚠️ Redis недоступен: {e}")

# Инициализация FastAPI
app = FastAPI(
    title="AgentFlow AI Clips API",
    description="Система генерации клипов с субтитрами",
    version="18.6.0"
)

# CORS настройки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Конфигурация для 512MB RAM
class Config:
    UPLOAD_DIR = "uploads"
    AUDIO_DIR = "audio"
    CLIPS_DIR = "clips"
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB (уменьшено для экономии памяти)
    MAX_TASK_AGE = 2 * 60 * 60  # 2 часа (уменьшено)
    CLEANUP_INTERVAL = 600  # Очистка каждые 10 минут
    MAX_MEMORY_USAGE = 400 * 1024 * 1024  # 400MB лимит (оставляем 112MB для системы)
    MAX_CONCURRENT_TASKS = 2  # Максимум 2 задачи одновременно

# Создание необходимых папок
for directory in [Config.UPLOAD_DIR, Config.AUDIO_DIR, Config.CLIPS_DIR]:
    os.makedirs(directory, exist_ok=True)

# Глобальные переменные
analysis_tasks = {}
generation_tasks = {}

# Инициализация OpenAI
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    logger.error("❌ OPENAI_API_KEY не найден в переменных окружения")
    raise ValueError("OPENAI_API_KEY обязателен")

client = OpenAI(api_key=openai_api_key)
logger.info("✅ OpenAI клиент инициализирован")

# Инициализация Supabase
supabase = None
service_supabase = None
SUPABASE_BUCKET = "video-results"

def init_supabase():
    """Инициализация Supabase клиентов"""
    global supabase, service_supabase
    if not SUPABASE_AVAILABLE:
        logger.warning("⚠️ Supabase не установлен")
        return False
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")
        supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not all([supabase_url, supabase_anon_key, supabase_service_key]):
            logger.warning("⚠️ Не все Supabase переменные настроены")
            return False
        supabase = create_client(supabase_url, supabase_anon_key)
        service_supabase = create_client(supabase_url, supabase_service_key)
        logger.info("✅ Supabase Storage подключен")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Supabase: {e}")
        return False

supabase_available = init_supabase()

# Функции для мониторинга памяти
def get_memory_usage() -> Dict[str, int]:
    """Получение информации об использовании памяти"""
    try:
        memory = psutil.virtual_memory()
        process = psutil.Process()
        return {
            "total_mb": memory.total // (1024 * 1024),
            "available_mb": memory.available // (1024 * 1024),
            "used_mb": memory.used // (1024 * 1024),
            "process_mb": process.memory_info().rss // (1024 * 1024),
            "percent": memory.percent
        }
    except Exception as e:
        logger.error(f"Ошибка получения информации о памяти: {e}")
        return {"total_mb": 512, "available_mb": 100, "used_mb": 412, "process_mb": 50, "percent": 80}

def check_memory_limit() -> bool:
    """Проверка лимита памяти"""
    try:
        memory_info = get_memory_usage()
        if memory_info["process_mb"] > (Config.MAX_MEMORY_USAGE // (1024 * 1024)):
            logger.warning(f"⚠️ Превышен лимит памяти: {memory_info['process_mb']}MB")
            return False
        return True
    except Exception:
        return True

def cleanup_old_files():
    """Очистка старых файлов для освобождения места"""
    try:
        current_time = datetime.now()
        cleaned_count = 0
        
        # Очистка старых видео
        for filename in os.listdir(Config.UPLOAD_DIR):
            file_path = os.path.join(Config.UPLOAD_DIR, filename)
            if os.path.isfile(file_path):
                file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                if (current_time - file_time).seconds > Config.MAX_TASK_AGE:
                    os.remove(file_path)
                    cleaned_count += 1
        
        # Очистка старых аудио файлов
        for filename in os.listdir(Config.AUDIO_DIR):
            file_path = os.path.join(Config.AUDIO_DIR, filename)
            if os.path.isfile(file_path):
                file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                if (current_time - file_time).seconds > Config.MAX_TASK_AGE:
                    os.remove(file_path)
                    cleaned_count += 1
        
        # Очистка старых клипов
        for filename in os.listdir(Config.CLIPS_DIR):
            file_path = os.path.join(Config.CLIPS_DIR, filename)
            if os.path.isfile(file_path):
                file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                if (current_time - file_time).seconds > Config.MAX_TASK_AGE:
                    os.remove(file_path)
                    cleaned_count += 1
        
        # Очистка старых задач из памяти
        tasks_to_remove = []
        for task_id, task in analysis_tasks.items():
            task_age = (current_time - task["created_at"]).seconds
            if task_age > Config.MAX_TASK_AGE:
                tasks_to_remove.append(task_id)
        
        for task_id in tasks_to_remove:
            del analysis_tasks[task_id]
            cleaned_count += 1
        
        if cleaned_count > 0:
            logger.info(f"🧹 Очищено {cleaned_count} старых файлов/задач")
        
        return cleaned_count
    except Exception as e:
        logger.error(f"Ошибка очистки файлов: {e}")
        return 0

# Главная страница
@app.get("/")
async def root():
    """Главная страница API"""
    return {
        "name": "AgentFlow AI Clips API",
        "version": "18.6.0",
        "status": "running",
        "description": "Система генерации клипов с субтитрами",
        "endpoints": {
            "upload": "/api/videos/upload",
            "analyze": "/api/videos/analyze", 
            "health": "/health",
            "stats": "/api/system/stats",
            "docs": "/docs"
        },
        "memory_optimized": "512MB RAM",
        "redis_available": REDIS_AVAILABLE
    }

# Добавляем эндпоинты для мониторинга
@app.get("/health")
async def health_check():
    """Проверка состояния системы"""
    try:
        memory_info = get_memory_usage()
        active_tasks = get_active_tasks_count()
        
        # Проверяем доступность ffmpeg
        ffmpeg_available = True
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, timeout=5)
        except:
            ffmpeg_available = False
        
        return {
            "status": "healthy",
            "memory": memory_info,
            "active_tasks": active_tasks,
            "max_concurrent_tasks": Config.MAX_CONCURRENT_TASKS,
            "ffmpeg_available": ffmpeg_available,
            "supabase_available": supabase_available,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/system/stats")
async def get_system_stats():
    """Получение статистики системы"""
    try:
        memory_info = get_memory_usage()
        active_tasks = get_active_tasks_count()
        
        # Подсчет файлов в папках
        upload_files = len([f for f in os.listdir(Config.UPLOAD_DIR) if os.path.isfile(os.path.join(Config.UPLOAD_DIR, f))])
        audio_files = len([f for f in os.listdir(Config.AUDIO_DIR) if os.path.isfile(os.path.join(Config.AUDIO_DIR, f))])
        clip_files = len([f for f in os.listdir(Config.CLIPS_DIR) if os.path.isfile(os.path.join(Config.CLIPS_DIR, f))])
        
        return {
            "memory": memory_info,
            "tasks": {
                "active": active_tasks,
                "total": len(analysis_tasks),
                "max_concurrent": Config.MAX_CONCURRENT_TASKS
            },
            "files": {
                "uploads": upload_files,
                "audio": audio_files,
                "clips": clip_files
            },
            "config": {
                "max_file_size_mb": Config.MAX_FILE_SIZE // (1024 * 1024),
                "max_memory_mb": Config.MAX_MEMORY_USAGE // (1024 * 1024),
                "cleanup_interval_min": Config.CLEANUP_INTERVAL // 60,
                "max_task_age_hours": Config.MAX_TASK_AGE // 3600
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/system/cleanup")
async def manual_cleanup():
    """Ручная очистка системы"""
    try:
        cleaned_count = cleanup_old_files()
        memory_info = get_memory_usage()
        
        return {
            "cleaned_files": cleaned_count,
            "memory_after_cleanup": memory_info,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/system/queue-stats")
async def get_queue_stats():
    """Статистика очереди задач"""
    try:
        queue_stats = hybrid_queue.get_queue_stats()
        memory_info = get_memory_usage()
        active_tasks = get_active_tasks_count()
        
        return {
            "queue": queue_stats,
            "memory": memory_info,
            "active_tasks": active_tasks,
            "redis_available": REDIS_AVAILABLE,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def get_active_tasks_count() -> int:
    """Подсчет активных задач"""
    active_count = 0
    for task in analysis_tasks.values():
        if task["status"] == "processing":
            active_count += 1
    return active_count

# Гибридная система очередей (работает с Redis и без него)
class HybridTaskQueue:
    """Гибридная очередь задач - Redis если доступен, иначе память"""
    
    def __init__(self):
        self.queue_name = "video_processing_queue"
        self.processing_set = "processing_tasks"
        self.results_prefix = "task_result:"
        self.memory_queue = []  # Fallback очередь в памяти
        self.memory_processing = set()  # Обрабатываемые задачи
        self.memory_results = {}  # Результаты в памяти
    
    def add_task(self, task_data: Dict) -> str:
        """Добавить задачу в очередь"""
        task_id = str(uuid.uuid4())
        task_data["task_id"] = task_id
        task_data["created_at"] = datetime.now().isoformat()
        
        if REDIS_AVAILABLE:
            try:
                redis_client.lpush(self.queue_name, json.dumps(task_data))
                logger.info(f"📝 Задача добавлена в Redis очередь: {task_id}")
                return task_id
            except Exception as e:
                logger.error(f"❌ Ошибка Redis, используем память: {e}")
        
        # Fallback в память
        self.memory_queue.append(task_data)
        logger.info(f"📝 Задача добавлена в память: {task_id}")
        return task_id
    
    def get_task(self) -> Optional[Dict]:
        """Получить задачу из очереди"""
        if REDIS_AVAILABLE:
            try:
                result = redis_client.brpop(self.queue_name, timeout=1)
                if result:
                    task_data = json.loads(result[1])
                    redis_client.sadd(self.processing_set, task_data["task_id"])
                    return task_data
            except Exception as e:
                logger.error(f"❌ Ошибка Redis: {e}")
        
        # Fallback в память
        if self.memory_queue:
            task_data = self.memory_queue.pop(0)
            self.memory_processing.add(task_data["task_id"])
            return task_data
        
        return None
    
    def complete_task(self, task_id: str, result: Dict):
        """Завершить задачу"""
        if REDIS_AVAILABLE:
            try:
                redis_client.setex(f"{self.results_prefix}{task_id}", 3600, json.dumps(result))
                redis_client.srem(self.processing_set, task_id)
                logger.info(f"✅ Задача завершена в Redis: {task_id}")
                return
            except Exception as e:
                logger.error(f"❌ Ошибка Redis: {e}")
        
        # Fallback в память
        self.memory_results[task_id] = result
        self.memory_processing.discard(task_id)
        logger.info(f"✅ Задача завершена в памяти: {task_id}")
    
    def get_task_result(self, task_id: str) -> Optional[Dict]:
        """Получить результат задачи"""
        if REDIS_AVAILABLE:
            try:
                result = redis_client.get(f"{self.results_prefix}{task_id}")
                if result:
                    return json.loads(result)
            except Exception as e:
                logger.error(f"❌ Ошибка Redis: {e}")
        
        # Fallback в память
        return self.memory_results.get(task_id)
    
    def get_queue_stats(self) -> Dict:
        """Статистика очереди"""
        if REDIS_AVAILABLE:
            try:
                return {
                    "queue_length": redis_client.llen(self.queue_name),
                    "processing": redis_client.scard(self.processing_set),
                    "redis_available": True,
                    "mode": "redis"
                }
            except Exception as e:
                logger.error(f"❌ Ошибка Redis: {e}")
        
        # Fallback в память
        return {
            "queue_length": len(self.memory_queue),
            "processing": len(self.memory_processing),
            "redis_available": False,
            "mode": "memory"
        }

# Глобальная гибридная очередь
hybrid_queue = HybridTaskQueue()

# Pydantic модели
class VideoAnalysisRequest(BaseModel):
    video_id: str

class ClipGenerationRequest(BaseModel):
    video_id: str
    format_id: str

class VideoInfo(BaseModel):
    id: str
    filename: str
    duration: float
    size: int
    status: str
    upload_time: str

class ClipInfo(BaseModel):
    id: str
    video_id: str
    format_id: str
    status: str
    progress: int
    current_stage: Optional[str] = None
    stage_progress: Optional[int] = None

def upload_clip_to_supabase(local_path: str, filename: str) -> str:
    """Загрузка клипа в Supabase Storage"""
    if not supabase_available or not service_supabase:
        logger.warning("⚠️ Supabase недоступен, возвращаем локальный путь")
        return f"/api/clips/download/{filename}"
    try:
        with open(local_path, "rb") as clip_file:
            storage_path = f"clips/{datetime.now().strftime('%Y%m%d')}/{filename}"
            response = service_supabase.storage.from_(SUPABASE_BUCKET).upload(
                storage_path, clip_file, {"content-type": "video/mp4"}
            )
            if response:
                public_url = service_supabase.storage.from_(SUPABASE_BUCKET).get_public_url(storage_path)
                logger.info(f"✅ Клип загружен в Supabase: {public_url}")
                return public_url
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки в Supabase: {e}")
    logger.warning("⚠️ Используется локальное хранение")
    return f"/api/clips/download/{filename}"

def get_video_duration(video_path: str) -> float:
    """Получение длительности видео"""
    try:
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data['format']['duration'])
    except Exception as e:
        logger.error(f"Ошибка получения длительности видео: {e}")
        return 60.0  # Fallback

def extract_audio(video_path: str, audio_path: str) -> bool:
    """Извлечение аудио из видео (оптимизировано для 512MB RAM)"""
    try:
        # Оптимизированная команда для экономии памяти
        cmd = [
            'ffmpeg', '-i', video_path, 
            '-vn',  # Без видео
            '-acodec', 'mp3', 
            '-ar', '16000',  # Низкая частота дискретизации
            '-ac', '1',  # Моно
            '-ab', '64k',  # Низкий битрейт для экономии памяти
            '-threads', '1',  # Один поток для экономии памяти
            '-y', audio_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
        return os.path.exists(audio_path)
    except subprocess.TimeoutExpired:
        logger.error("❌ Таймаут при извлечении аудио")
        return False
    except Exception as e:
        logger.error(f"Ошибка извлечения аудио: {e}")
        return False

def safe_transcribe_audio(audio_path: str) -> Optional[Dict]:
    """Безопасная транскрибация аудио"""
    try:
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["word"]
            )
            return transcript.model_dump() if hasattr(transcript, 'model_dump') else dict(transcript)
    except Exception as e:
        logger.error(f"Ошибка транскрибации: {e}")
        return None

def analyze_with_chatgpt(transcript_text: str, video_duration: float) -> Optional[Dict]:
    """Анализ транскрипта для получения 3-5 клипов"""
    try:
        target_clips = 2 if video_duration <= 30 else 3 if video_duration <= 60 else 4 if video_duration <= 120 else 5
        prompt = f"""
Проанализируй этот транскрипт видео длительностью {video_duration:.1f} секунд и найди {target_clips} самых интересных моментов для коротких клипов.

Транскрипт: {transcript_text}

ТРЕБОВАНИЯ:
1. Создай РОВНО {target_clips} клипов
2. Каждый клип должен быть 15-20 секунд
3. Клипы НЕ должны пересекаться по времени
4. Выбирай самые яркие, эмоциональные или информативные моменты
5. Если контента мало, равномерно распредели клипы по всему видео
6. Время клипов должно быть в пределах 0-{video_duration:.1f} секунд

Верни результат СТРОГО в JSON формате:
{{
    "highlights": [
        {{
            "start_time": 0,
            "end_time": 18,
            "title": "Интересный заголовок",
            "description": "Краткое описание содержания",
            "keywords": ["ключевое", "слово"]
        }}
    ]
}}
"""
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.7
        )
        content = response.choices[0].message.content.strip()
        if content.startswith('```json'):
            content = content[7:]
        if content.endswith('```'):
            content = content[:-3]
        content = content.strip()
        try:
            result = json.loads(content)
            highlights = result.get("highlights", [])
            if len(highlights) < target_clips:
                logger.warning(f"ChatGPT вернул {len(highlights)} клипов вместо {target_clips}")
                last_end = highlights[-1]["end_time"] if highlights else 0
                while len(highlights) < target_clips and last_end + 20 <= video_duration:
                    highlights.append({
                        "start_time": last_end + 2,
                        "end_time": min(last_end + 20, video_duration),
                        "title": f"Клип {len(highlights) + 1}",
                        "description": "Дополнительный клип",
                        "keywords": []
                    })
                    last_end = highlights[-1]["end_time"]
            return {"highlights": highlights}
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            return create_fallback_highlights(video_duration, target_clips)
    except Exception as e:
        logger.error(f"Ошибка анализа с ChatGPT: {e}")
        return create_fallback_highlights(video_duration, 3)

def create_fallback_highlights(video_duration: float, target_clips: int) -> Dict:
    """Создание fallback клипов"""
    highlights = []
    clip_duration = 18
    gap = 2
    for i in range(target_clips):
        start = i * (clip_duration + gap)
        end = start + clip_duration
        if end > video_duration:
            end = video_duration
            start = max(0, end - clip_duration)
        if start >= video_duration - 5:
            break
        highlights.append({
            "start_time": start,
            "end_time": end,
            "title": f"Клип {i+1}",
            "description": "Автоматически созданный клип",
            "keywords": []
        })
    return {"highlights": highlights}

# Модели данных
class VideoUploadResponse(BaseModel):
    video_id: str
    filename: str
    size: int
    duration: float

class AnalyzeRequest(BaseModel):
    video_id: str

class ClipGenerateRequest(BaseModel):
    video_id: str
    format_id: str = "9x16"  # 9x16, 16x9, 1x1, 4x5
    style_id: str = "modern"  # modern, neon, fire, elegant

class ClipDataResponse(BaseModel):
    task_id: str
    video_id: str
    format_id: str
    style_id: str
    download_url: str
    highlights: List[Dict]
    transcript: List[Dict]
    video_duration: float

# API эндпоинты
@app.post("/api/videos/upload", response_model=VideoUploadResponse)
async def upload_video(file: UploadFile = File(...)):
    """Загрузка видео файла с проверкой памяти"""
    try:
        # Проверка памяти перед загрузкой
        if not check_memory_limit():
            cleanup_old_files()
            if not check_memory_limit():
                raise HTTPException(status_code=507, detail="Недостаточно памяти на сервере")
        
        # Проверка размера файла
        if file.size > Config.MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"Файл слишком большой. Максимум {Config.MAX_FILE_SIZE // (1024*1024)}MB")
        
        # Генерация уникального ID
        video_id = str(uuid.uuid4())
        filename = f"{video_id}_{file.filename}"
        file_path = os.path.join(Config.UPLOAD_DIR, filename)
        
        # Сохранение файла чанками для экономии памяти
        with open(file_path, "wb") as buffer:
            while True:
                chunk = await file.read(8192)  # Читаем по 8KB
                if not chunk:
                    break
                buffer.write(chunk)
        
        # Получение длительности видео
        duration = get_video_duration(file_path)
        
        # Логирование с информацией о памяти
        memory_info = get_memory_usage()
        logger.info(f"✅ Видео загружено: {filename}, размер: {file.size//1024}KB, длительность: {duration}s, память: {memory_info['process_mb']}MB")
        
        return VideoUploadResponse(
            video_id=video_id,
            filename=filename,
            size=file.size,
            duration=duration
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки видео: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/videos/analyze")
async def analyze_video(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Запуск анализа видео с проверкой ресурсов"""
    try:
        # Проверка памяти и количества активных задач
        if not check_memory_limit():
            cleanup_old_files()
            if not check_memory_limit():
                raise HTTPException(status_code=507, detail="Недостаточно памяти для анализа")
        
        active_tasks = get_active_tasks_count()
        if active_tasks >= Config.MAX_CONCURRENT_TASKS:
            raise HTTPException(status_code=429, detail=f"Слишком много активных задач ({active_tasks}). Попробуйте позже.")
        
        task_id = str(uuid.uuid4())
        
        # Запуск фоновой задачи анализа
        background_tasks.add_task(analyze_video_task, task_id, request.video_id)
        
        # Сохранение статуса задачи
        analysis_tasks[task_id] = {
            "status": "processing",
            "video_id": request.video_id,
            "created_at": datetime.now(),
            "progress": 0
        }
        
        memory_info = get_memory_usage()
        logger.info(f"🔍 Запущен анализ видео: {request.video_id}, task_id: {task_id}, память: {memory_info['process_mb']}MB, активных задач: {active_tasks + 1}")
        
        return {"task_id": task_id, "status": "processing"}
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска анализа: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/videos/{video_id}/status")
async def get_video_status(video_id: str):
    """Получение статуса анализа видео"""
    try:
        # Ищем задачу по video_id
        task = None
        task_id = None
        for tid, t in analysis_tasks.items():
            if t["video_id"] == video_id:
                task = t
                task_id = tid
                break
        
        if not task:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        
        return {
            "task_id": task_id,
            "video_id": video_id,
            "status": task["status"],
            "progress": task.get("progress", 0),
            "result": task.get("result"),
            "error": task.get("error")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка получения статуса: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/videos/download/{filename}")
async def download_video(filename: str):
    """Скачивание видео файла (оригинал или клип)"""
    try:
        # Сначала ищем в папке клипов
        clip_path = os.path.join(Config.CLIPS_DIR, filename)
        if os.path.exists(clip_path):
            logger.info(f"📥 Скачивание клипа: {filename}")
            return FileResponse(
                clip_path,
                media_type="video/mp4",
                filename=filename
            )
        
        # Если не найден в клипах, ищем в оригинальных видео
        video_path = os.path.join(Config.UPLOAD_DIR, filename)
        if os.path.exists(video_path):
            logger.info(f"📥 Скачивание оригинального видео: {filename}")
            return FileResponse(
                video_path,
                media_type="video/mp4",
                filename=filename
            )
        
        # Файл не найден нигде
        raise HTTPException(status_code=404, detail="Файл не найден")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания файла: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/clips/generate", response_model=ClipDataResponse)
async def generate_clips_data(request: ClipGenerateRequest):
    """Генерация клипов с нарезкой видео на бэкенде (с fallback)"""
    try:
        # Проверяем что анализ завершен
        task = None
        for t in analysis_tasks.values():
            if t["video_id"] == request.video_id and t["status"] == "completed":
                task = t
                break
        
        if not task:
            raise HTTPException(status_code=400, detail="Анализ видео не завершен")
        
        result = task["result"]
        
        # Находим файл видео
        video_files = [f for f in os.listdir(Config.UPLOAD_DIR) if f.startswith(request.video_id)]
        if not video_files:
            raise HTTPException(status_code=404, detail="Видео файл не найден")
        
        video_path = os.path.join(Config.UPLOAD_DIR, video_files[0])
        video_filename = video_files[0]
        
        # Генерируем task_id для отслеживания
        task_id = str(uuid.uuid4())
        
        logger.info(f"🎬 Попытка нарезки видео на клипы: {request.video_id}")
        
        # Пытаемся нарезать видео на клипы
        try:
            clips_data = await cut_video_into_clips(
                video_path=video_path,
                highlights=result["highlights"],
                transcript=result["transcript"],
                video_id=request.video_id,
                format_id=request.format_id
            )
            
            if clips_data and len(clips_data) > 0:
                logger.info(f"✅ Клипы созданы: {len(clips_data)} штук")
                
                return ClipDataResponse(
                    task_id=task_id,
                    video_id=request.video_id,
                    format_id=request.format_id,
                    style_id=request.style_id,
                    download_url="",  # Не используется для клипов
                    highlights=clips_data,  # Данные о клипах
                    transcript=result["transcript"],
                    video_duration=result["video_duration"]
                )
            else:
                raise Exception("Не удалось создать клипы")
                
        except Exception as cutting_error:
            logger.warning(f"⚠️ Ошибка нарезки видео: {cutting_error}")
            logger.info("🔄 Переключаемся на старый режим (без нарезки)")
            
            # Fallback: возвращаем старый формат без нарезки
            download_url = f"/api/videos/download/{video_filename}"
            
            # Подготавливаем субтитры для каждого хайлайта (без нарезки видео)
            enhanced_highlights = []
            for i, highlight in enumerate(result["highlights"]):
                clip_subtitles = prepare_clip_subtitles(
                    transcript=result["transcript"],
                    start_time=highlight["start_time"],
                    end_time=highlight["end_time"]
                )
                
                enhanced_highlight = {
                    **highlight,
                    "clip_id": f"{request.video_id}_clip_{i+1}",
                    "video_url": download_url,  # Одно видео для всех
                    "duration": highlight["end_time"] - highlight["start_time"],
                    "subtitles": clip_subtitles,
                    "format_id": request.format_id,
                    "needs_client_cutting": True  # Флаг для фронтенда
                }
                enhanced_highlights.append(enhanced_highlight)
            
            logger.info(f"📊 Подготовлены данные для генерации клипов (старый режим): {request.video_id}")
            
            return ClipDataResponse(
                task_id=task_id,
                video_id=request.video_id,
                format_id=request.format_id,
                style_id=request.style_id,
                download_url=download_url,
                highlights=enhanced_highlights,
                transcript=result["transcript"],
                video_duration=result["video_duration"]
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка генерации клипов: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def cut_video_into_clips(video_path: str, highlights: List[Dict], transcript: List[Dict], video_id: str, format_id: str) -> List[Dict]:
    """Нарезает видео на отдельные клипы"""
    clips_data = []
    
    for i, highlight in enumerate(highlights):
        try:
            clip_id = f"{video_id}_clip_{i+1}"
            clip_filename = f"{clip_id}.mp4"
            clip_path = os.path.join(Config.CLIPS_DIR, clip_filename)
            
            # Нарезаем видео с помощью ffmpeg
            success = cut_video_segment(
                input_path=video_path,
                output_path=clip_path,
                start_time=highlight["start_time"],
                end_time=highlight["end_time"],
                format_id=format_id
            )
            
            if not success:
                logger.error(f"❌ Ошибка нарезки клипа {clip_id}")
                continue
            
            # Подготавливаем субтитры для этого клипа
            clip_subtitles = prepare_clip_subtitles(
                transcript=transcript,
                start_time=highlight["start_time"],
                end_time=highlight["end_time"]
            )
            
            # Загружаем клип в Supabase (если доступен)
            video_url = upload_clip_to_supabase(clip_path, clip_filename)
            
            # Создаем данные клипа
            clip_data = {
                **highlight,  # Сохраняем оригинальные данные хайлайта
                "clip_id": clip_id,
                "video_url": video_url,  # Используем URL из Supabase или локальный
                "duration": highlight["end_time"] - highlight["start_time"],
                "subtitles": clip_subtitles,
                "format_id": format_id
            }
            
            clips_data.append(clip_data)
            logger.info(f"✅ Клип создан: {clip_id} ({clip_data['duration']:.1f}s)")
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания клипа {i+1}: {e}")
            continue
    
    return clips_data

def cut_video_segment(input_path: str, output_path: str, start_time: float, end_time: float, format_id: str) -> bool:
    """Нарезает сегмент видео с помощью ffmpeg (оптимизировано для 512MB RAM)"""
    try:
        # Проверяем память перед началом
        if not check_memory_limit():
            logger.warning("⚠️ Недостаточно памяти для нарезки видео")
            return False
        
        # Проверяем что ffmpeg доступен
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("❌ ffmpeg не найден на сервере")
            return False
        
        # Получаем параметры обрезки для формата
        crop_params = get_crop_parameters_for_format(format_id)
        
        # Оптимизированная команда ffmpeg для экономии памяти
        cmd = [
            "ffmpeg", "-y",  # Перезаписывать файлы
            "-i", input_path,  # Входной файл
            "-ss", str(start_time),  # Время начала
            "-t", str(end_time - start_time),  # Длительность
            "-vf", f"scale={crop_params['width']}:{crop_params['height']}:force_original_aspect_ratio=increase,crop={crop_params['width']}:{crop_params['height']}",
            "-c:v", "libx264",  # Видео кодек
            "-c:a", "aac",  # Аудио кодек
            "-preset", "ultrafast",  # Самое быстрое кодирование (экономит память)
            "-crf", "28",  # Более высокое сжатие для экономии места
            "-threads", "1",  # Один поток для экономии памяти
            "-bufsize", "1M",  # Маленький буфер
            "-maxrate", "1M",  # Ограничение битрейта
            output_path
        ]
        
        # Выполняем команду с таймаутом
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        
        if result.returncode == 0 and os.path.exists(output_path):
            logger.info(f"✅ Видео сегмент создан: {output_path}")
            return True
        else:
            logger.error(f"❌ Ошибка ffmpeg: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("❌ Таймаут при нарезке видео")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка нарезки видео: {e}")
        return False

def get_crop_parameters_for_format(format_id: str) -> Dict[str, int]:
    """Возвращает параметры обрезки для разных форматов"""
    formats = {
        "9x16": {"width": 720, "height": 1280},  # TikTok/Instagram Stories
        "16x9": {"width": 1280, "height": 720},  # YouTube/Landscape
        "1x1": {"width": 720, "height": 720},    # Instagram Post
        "4x5": {"width": 720, "height": 900}     # Instagram Portrait
    }
    return formats.get(format_id, formats["9x16"])

def prepare_clip_subtitles(transcript: List[Dict], start_time: float, end_time: float) -> List[Dict]:
    """Подготавливает субтитры для конкретного клипа"""
    # Фильтруем слова для этого временного диапазона
    clip_words = [
        word for word in transcript 
        if word.get("start", 0) >= start_time and word.get("end", 0) <= end_time
    ]
    
    # Корректируем время относительно начала клипа
    adjusted_words = []
    for word in clip_words:
        adjusted_word = {
            **word,
            "start": word.get("start", 0) - start_time,
            "end": word.get("end", 0) - start_time
        }
        adjusted_words.append(adjusted_word)
    
    # Группируем слова в субтитры по 3-5 слов
    subtitles = group_words_into_subtitles(adjusted_words, words_per_group=4)
    
    logger.info(f"📝 Подготовлено {len(subtitles)} субтитров для клипа ({start_time:.1f}s - {end_time:.1f}s)")
    
    return subtitles

def group_words_into_subtitles(words: List[Dict], words_per_group: int = 4) -> List[Dict]:
    """Группирует слова в субтитры"""
    subtitles = []
    
    for i in range(0, len(words), words_per_group):
        group = words[i:i + words_per_group]
        
        if group:
            subtitle = {
                "id": f"subtitle_{i // words_per_group}",
                "start": group[0].get("start", 0),
                "end": group[-1].get("end", 0),
                "text": " ".join(word.get("word", "") for word in group),
                "words": group  # Для караоке эффекта
            }
            subtitles.append(subtitle)
    
    return subtitles

@app.get("/api/videos/{video_id}/export-data")
async def get_export_data(video_id: str):
    """Получение всех данных для экспорта (альтернативный эндпоинт)"""
    try:
        # Находим завершенную задачу анализа
        task = None
        for t in analysis_tasks.values():
            if t["video_id"] == video_id and t["status"] == "completed":
                task = t
                break
        
        if not task:
            raise HTTPException(status_code=400, detail="Анализ видео не завершен")
        
        result = task["result"]
        
        # Находим файл видео
        video_files = [f for f in os.listdir(Config.UPLOAD_DIR) if f.startswith(video_id)]
        if not video_files:
            raise HTTPException(status_code=404, detail="Видео файл не найден")
        
        video_filename = video_files[0]
        
        return {
            "video_id": video_id,
            "video_filename": video_filename,
            "download_url": f"/api/videos/download/{video_filename}",
            "highlights": result["highlights"],
            "transcript": result["transcript"],
            "video_duration": result["video_duration"],
            "analysis_completed_at": task.get("completed_at")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка получения данных для экспорта: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Фоновая задача анализа видео
async def analyze_video_task(task_id: str, video_id: str):
    """Фоновая задача анализа видео"""
    try:
        logger.info(f"🔍 Начат анализ видео: {video_id}")
        
        # Обновляем прогресс
        analysis_tasks[task_id]["progress"] = 10
        
        # Находим видео файл
        video_files = [f for f in os.listdir(Config.UPLOAD_DIR) if f.startswith(video_id)]
        if not video_files:
            raise Exception("Видео файл не найден")
        
        video_path = os.path.join(Config.UPLOAD_DIR, video_files[0])
        
        # Извлечение аудио
        analysis_tasks[task_id]["progress"] = 20
        audio_path = os.path.join(Config.AUDIO_DIR, f"{video_id}.wav")
        if not extract_audio(video_path, audio_path):
            raise Exception("Ошибка извлечения аудио")
        
        # Транскрипция
        analysis_tasks[task_id]["progress"] = 50
        transcript_result = safe_transcribe_audio(audio_path)
        if not transcript_result:
            raise Exception("Ошибка транскрипции")
        
        # Анализ с ChatGPT
        analysis_tasks[task_id]["progress"] = 80
        video_duration = get_video_duration(video_path)
        
        # Правильная обработка структуры транскрипта
        if "words" in transcript_result:
            # Новый формат OpenAI API с word-level timestamps
            transcript_text = " ".join([word["word"] for word in transcript_result["words"]])
            transcript_words = transcript_result["words"]
        elif "segments" in transcript_result:
            # Старый формат с сегментами
            transcript_text = " ".join([segment["text"] for segment in transcript_result["segments"]])
            transcript_words = []
            for segment in transcript_result["segments"]:
                if "words" in segment:
                    transcript_words.extend(segment["words"])
        else:
            # Fallback - используем текст напрямую
            transcript_text = transcript_result.get("text", "")
            transcript_words = []
        
        logger.info(f"📝 Транскрипт получен: {len(transcript_text)} символов, {len(transcript_words)} слов")
        
        analysis_result = analyze_with_chatgpt(transcript_text, video_duration)
        if not analysis_result:
            # Создаем fallback хайлайты
            analysis_result = create_fallback_highlights(video_duration, 3)
        
        # Завершение
        analysis_tasks[task_id].update({
            "status": "completed",
            "progress": 100,
            "completed_at": datetime.now(),
            "result": {
                "highlights": analysis_result["highlights"],
                "transcript": transcript_words,  # Используем слова с временными метками
                "video_duration": video_duration
            }
        })
        
        logger.info(f"✅ Анализ завершен: {video_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка анализа видео {video_id}: {e}")
        analysis_tasks[task_id].update({
            "status": "failed",
            "error": str(e)
        })

def get_crop_parameters(width: int, height: int, format_type: str) -> dict:
    """Возвращает параметры обрезки для разных форматов"""
    formats = {
        "9:16": {"target_width": 720, "target_height": 1280},
        "16:9": {"target_width": 1280, "target_height": 720},
        "1:1": {"target_width": 720, "target_height": 720},
        "4:5": {"target_width": 720, "target_height": 900}
    }
    target = formats.get(format_type, formats["9:16"])
    scale_x = target["target_width"] / width
    scale_y = target["target_height"] / height
    scale = max(scale_x, scale_y)
    new_width = int(width * scale)
    new_height = int(height * scale)
    crop_x = (new_width - target["target_width"]) // 2
    crop_y = (new_height - target["target_height"]) // 2
    return {
        "width": target["target_width"],
        "height": target["target_height"]
    }

# Автоматическая очистка памяти
import threading
import time

def periodic_cleanup():
    """Периодическая очистка системы"""
    while True:
        try:
            time.sleep(Config.CLEANUP_INTERVAL)
            memory_info = get_memory_usage()
            
            # Если память заканчивается, запускаем агрессивную очистку
            if memory_info["process_mb"] > (Config.MAX_MEMORY_USAGE // (1024 * 1024)) * 0.8:
                logger.warning(f"⚠️ Высокое потребление памяти: {memory_info['process_mb']}MB")
                cleaned = cleanup_old_files()
                logger.info(f"🧹 Автоочистка: удалено {cleaned} файлов")
            
        except Exception as e:
            logger.error(f"Ошибка автоочистки: {e}")

# Запуск фонового процесса очистки
cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
cleanup_thread.start()

# Запуск приложения
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    
    # Логирование конфигурации для 512MB RAM
    memory_info = get_memory_usage()
    logger.info(f"🚀 AgentFlow AI Clips v18.6.0 запущен!")
    logger.info(f"💾 Память: {memory_info['process_mb']}MB / {memory_info['total_mb']}MB")
    logger.info(f"⚙️ Конфигурация для 512MB RAM:")
    logger.info(f"   - Максимум файла: {Config.MAX_FILE_SIZE // (1024*1024)}MB")
    logger.info(f"   - Лимит памяти: {Config.MAX_MEMORY_USAGE // (1024*1024)}MB")
    logger.info(f"   - Максимум задач: {Config.MAX_CONCURRENT_TASKS}")
    logger.info(f"   - Очистка каждые: {Config.CLEANUP_INTERVAL // 60} минут")
    logger.info(f"📊 Система готова к обработке видео")
    
    uvicorn.run(app, host="0.0.0.0", port=port)

