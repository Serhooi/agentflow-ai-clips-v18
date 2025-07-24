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
    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", "250")) * 1024 * 1024  # Настраиваемый лимит
    MAX_TASK_AGE = 4 * 60 * 60  # 4 часа (для длинных видео)
    CLEANUP_INTERVAL = 600  # Очистка каждые 10 минут
    MAX_MEMORY_USAGE = 600 * 1024 * 1024  # 600MB лимит (для больших видео)
    MAX_CONCURRENT_TASKS = 2  # Максимум 2 задачи одновременно
    CLIP_MIN_DURATION = int(os.getenv("CLIP_MIN_DURATION", "40"))  # Минимальная длительность клипов
    CLIP_MAX_DURATION = int(os.getenv("CLIP_MAX_DURATION", "80"))  # Максимальная длительность клипов
    FFMPEG_TIMEOUT_MULTIPLIER = int(os.getenv("FFMPEG_TIMEOUT_MULTIPLIER", "4"))  # Множитель таймаута для ffmpeg
    CONTENT_LANGUAGE = os.getenv("CONTENT_LANGUAGE", "ru")  # Язык контента (ru/en)

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
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
        return os.path.exists(audio_path)
    except subprocess.TimeoutExpired:
        logger.error("❌ Таймаут при извлечении аудио")
        return False
    except Exception as e:
        logger.error(f"Ошибка извлечения аудио: {e}")
        return False

def safe_transcribe_audio(audio_path: str) -> Optional[Dict]:
    """Безопасная транскрибация аудио с поддержкой вставных слов"""
    try:
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["word"],
                # Промпт для включения вставных слов и междометий
                prompt="Transcribe everything including all filler words, hesitations, and interjections: um, uh, ah, oh, hmm, yeah, yep, yes, no, like, you know, I mean, so, well, actually, basically, literally, right, okay, alright, wow, hey, man, dude, guys, folks, people, anyway, whatever, honestly, seriously, obviously, definitely, probably, maybe, perhaps, indeed, certainly, absolutely, exactly, totally, completely, really, very, quite, just, only, even, still, already, yet, now, then, here, there, this, that, these, those."
            )
            result = transcript.model_dump() if hasattr(transcript, 'model_dump') else dict(transcript)
            
            # Диагностика транскрипции
            diagnose_transcript_issues(result)
            
            # Постобработка для улучшения распознавания вставных слов
            if 'words' in result:
                result['words'] = enhance_filler_words(result['words'])
            
            return result
    except Exception as e:
        logger.error(f"Ошибка транскрибации: {e}")
        return None

def enhance_filler_words(words: List[Dict]) -> List[Dict]:
    """Улучшает распознавание вставных слов и междометий"""
    enhanced_words = []
    corrections_made = 0
    filler_words_found = 0
    
    # Словарь для исправления часто неправильно распознанных вставных слов
    filler_corrections = {
        'um': ['uhm', 'umm', 'uum', 'em'],
        'uh': ['uhh', 'uuh', 'ah'],
        'yeah': ['yah', 'yea', 'ye'],
        'like': ['lyk', 'lik'],
        'you know': ['ya know', 'y\'know', 'yknow'],
        'so': ['soo', 'sooo'],
        'well': ['wel', 'wll'],
        'actually': ['actualy', 'acually'],
        'basically': ['basicaly', 'basicly'],
        'literally': ['literaly', 'literaly'],
        'right': ['rite', 'rght'],
        'okay': ['ok', 'okk', 'okey'],
        'alright': ['aright', 'alrite', 'all right'],
        'hmm': ['hm', 'hmm', 'hmmm'],
        'oh': ['ooh', 'ohh'],
        'wow': ['woow', 'wooow'],
        'hey': ['hei', 'heyy'],
        'man': ['mn'],
        'dude': ['dud'],
        'guys': ['gys'],
        'folks': ['folx'],
        'people': ['ppl', 'peple']
    }
    
    # Список всех вставных слов для подсчета
    all_filler_words = ['um', 'uh', 'yeah', 'like', 'you know', 'so', 'well', 'actually', 'basically', 'literally', 'right', 'okay', 'alright', 'hmm', 'oh', 'wow', 'hey', 'man', 'dude', 'guys', 'folks', 'people']
    
    for word in words:
        word_text = word.get('word', '').strip().lower()
        original_word = word_text
        
        # Проверяем нужно ли исправить слово
        corrected = False
        for correct_word, variations in filler_corrections.items():
            if word_text in variations:
                word['word'] = correct_word
                corrections_made += 1
                corrected = True
                logger.debug(f"🔧 Исправлено: '{original_word}' → '{correct_word}'")
                break
        
        # Подсчитываем вставные слова
        if word_text in all_filler_words or any(word_text in variations for variations in filler_corrections.values()):
            filler_words_found += 1
        
        # Добавляем слово в результат
        enhanced_words.append(word)
    
    logger.info(f"📝 Обработано {len(enhanced_words)} слов: {corrections_made} исправлений, {filler_words_found} вставных слов найдено")
    return enhanced_words

def analyze_content_type(transcript_text: str) -> str:
    """Анализирует тип контента для оптимизации поиска клипов"""
    text_lower = transcript_text.lower()
    
    # Подсчитываем ключевые слова для разных типов контента
    educational_keywords = ['learn', 'teach', 'explain', 'understand', 'knowledge', 'study', 'lesson', 'course', 'tutorial', 'guide', 'how to', 'step by step', 'method', 'technique', 'process', 'theory', 'concept', 'principle', 'definition', 'example']
    entertainment_keywords = ['funny', 'hilarious', 'joke', 'laugh', 'comedy', 'entertainment', 'fun', 'amusing', 'humor', 'story', 'adventure', 'exciting', 'amazing', 'incredible', 'unbelievable', 'crazy', 'wild', 'epic', 'awesome', 'fantastic']
    business_keywords = ['business', 'money', 'profit', 'investment', 'strategy', 'marketing', 'sales', 'growth', 'success', 'entrepreneur', 'startup', 'company', 'market', 'customer', 'revenue', 'finance', 'economy', 'industry', 'competition', 'opportunity']
    personal_keywords = ['life', 'experience', 'personal', 'journey', 'story', 'challenge', 'overcome', 'struggle', 'achievement', 'goal', 'dream', 'motivation', 'inspiration', 'advice', 'wisdom', 'lesson learned', 'mistake', 'failure', 'success', 'growth']
    tech_keywords = ['technology', 'software', 'app', 'digital', 'internet', 'computer', 'programming', 'code', 'development', 'innovation', 'artificial intelligence', 'ai', 'machine learning', 'data', 'algorithm', 'system', 'platform', 'tool', 'feature', 'update']
    
    # Подсчитываем совпадения
    educational_score = sum(1 for keyword in educational_keywords if keyword in text_lower)
    entertainment_score = sum(1 for keyword in entertainment_keywords if keyword in text_lower)
    business_score = sum(1 for keyword in business_keywords if keyword in text_lower)
    personal_score = sum(1 for keyword in personal_keywords if keyword in text_lower)
    tech_score = sum(1 for keyword in tech_keywords if keyword in text_lower)
    
    # Определяем тип контента
    scores = {
        'educational': educational_score,
        'entertainment': entertainment_score,
        'business': business_score,
        'personal': personal_score,
        'tech': tech_score
    }
    
    content_type = max(scores, key=scores.get)
    logger.info(f"🎯 Определен тип контента: {content_type} (score: {scores[content_type]})")
    
    return content_type

def analyze_content_value(transcript_text: str) -> Dict:
    """Анализирует ценность контента для аудитории"""
    text_lower = transcript_text.lower()
    
    # Индикаторы высокой ценности
    value_indicators = {
        'actionable_advice': 0,
        'specific_numbers': 0,
        'personal_stories': 0,
        'expert_insights': 0,
        'problem_solutions': 0,
        'surprising_facts': 0,
        'practical_tips': 0,
        'emotional_moments': 0
    }
    
    # Слова, указывающие на практические советы
    actionable_words = ['how to', 'step by step', 'here\'s what', 'you should', 'you need to', 'the key is', 'the secret is', 'what works', 'what doesn\'t work', 'avoid this', 'do this instead', 'try this', 'use this']
    value_indicators['actionable_advice'] = sum(1 for word in actionable_words if word in text_lower)
    
    # Конкретные числа и статистика
    import re
    numbers = re.findall(r'\b\d+(?:\.\d+)?(?:%|percent|million|billion|thousand|dollars?|years?|months?|days?|hours?|minutes?)\b', text_lower)
    value_indicators['specific_numbers'] = len(numbers)
    
    # Личные истории и опыт
    story_words = ['when i', 'i remember', 'my experience', 'what happened', 'i learned', 'i discovered', 'i realized', 'my mistake', 'i failed', 'i succeeded']
    value_indicators['personal_stories'] = sum(1 for word in story_words if word in text_lower)
    
    # Экспертные инсайты
    expert_words = ['research shows', 'studies prove', 'data reveals', 'according to', 'experts say', 'the truth is', 'what most people don\'t know', 'insider secret', 'industry secret']
    value_indicators['expert_insights'] = sum(1 for word in expert_words if word in text_lower)
    
    # Решения проблем
    solution_words = ['solution', 'fix this', 'solve', 'problem', 'challenge', 'overcome', 'breakthrough', 'game changer', 'this changed everything']
    value_indicators['problem_solutions'] = sum(1 for word in solution_words if word in text_lower)
    
    # Удивительные факты
    surprise_words = ['surprising', 'shocking', 'unbelievable', 'amazing', 'incredible', 'you won\'t believe', 'most people think', 'contrary to', 'opposite of']
    value_indicators['surprising_facts'] = sum(1 for word in surprise_words if word in text_lower)
    
    # Практические советы
    tip_words = ['tip', 'trick', 'hack', 'shortcut', 'faster way', 'easier way', 'better way', 'pro tip', 'life hack', 'quick fix']
    value_indicators['practical_tips'] = sum(1 for word in tip_words if word in text_lower)
    
    # Эмоциональные моменты
    emotion_words = ['excited', 'frustrated', 'angry', 'happy', 'sad', 'disappointed', 'thrilled', 'nervous', 'confident', 'proud', 'embarrassed']
    value_indicators['emotional_moments'] = sum(1 for word in emotion_words if word in text_lower)
    
    total_value_score = sum(value_indicators.values())
    logger.info(f"💎 Анализ ценности контента: общий балл {total_value_score}, топ категории: {sorted(value_indicators.items(), key=lambda x: x[1], reverse=True)[:3]}")
    
    return value_indicators

def identify_key_moments(transcript_text: str) -> List[str]:
    """Определяет ключевые моменты в тексте"""
    text_lower = transcript_text.lower()
    
    # Фразы, указывающие на важные моменты
    key_moment_indicators = [
        'the most important thing',
        'here\'s the key',
        'this is crucial',
        'pay attention to this',
        'this changed everything',
        'the breakthrough moment',
        'the turning point',
        'what i wish i knew',
        'the biggest mistake',
        'the secret is',
        'here\'s what works',
        'the truth about',
        'what nobody tells you',
        'the real reason',
        'this will blow your mind',
        'game changer',
        'life changing',
        'this is huge'
    ]
    
    found_moments = []
    for indicator in key_moment_indicators:
        if indicator in text_lower:
            found_moments.append(indicator)
    
    logger.info(f"🔑 Найдено ключевых моментов: {len(found_moments)} - {found_moments[:5]}")
    return found_moments

def calculate_clip_quality_score(highlight: Dict, transcript_text: str) -> float:
    """Рассчитывает оценку качества клипа с фокусом на реальную ценность для аудитории"""
    score = 0.0
    
    # Базовая оценка за длительность (оптимально 45-60 секунд)
    duration = highlight.get("duration", highlight["end_time"] - highlight["start_time"])
    if 45 <= duration <= 60:
        score += 2.0
    elif 30 <= duration <= 75:
        score += 1.5
    else:
        score += 1.0
    
    # Оценка за практическую ценность (ГЛАВНЫЙ КРИТЕРИЙ)
    title = highlight.get("title", "").lower()
    description = highlight.get("description", "").lower()
    hook = highlight.get("hook", "").lower()
    climax = highlight.get("climax", "").lower()
    
    all_text = f"{title} {description} {hook} {climax}"
    
    # Высокоценные индикаторы (по 2 балла каждый)
    high_value_indicators = [
        "how to", "step by step", "secret", "mistake", "avoid", "solution",
        "works", "doesn't work", "key", "important", "crucial", "breakthrough",
        "game changer", "life changing", "truth about", "real reason"
    ]
    high_value_score = sum(2.0 for indicator in high_value_indicators if indicator in all_text)
    score += min(high_value_score, 8.0)  # Максимум 8 баллов
    
    # Практические индикаторы (по 1.5 балла каждый)
    practical_indicators = [
        "tip", "trick", "hack", "advice", "recommend", "suggest",
        "use this", "try this", "do this", "example", "case study"
    ]
    practical_score = sum(1.5 for indicator in practical_indicators if indicator in all_text)
    score += min(practical_score, 6.0)  # Максимум 6 баллов
    
    # Эмоциональная ценность
    emotion = highlight.get("emotion", "neutral").lower()
    emotion_scores = {
        "inspiration": 3.0, "surprise": 2.5, "excitement": 2.5,
        "curiosity": 2.0, "humor": 2.0, "interest": 1.5, "neutral": 0.5
    }
    score += emotion_scores.get(emotion, 1.0)
    
    # Вирусный потенциал (меньший вес, чем ценность)
    viral_potential = highlight.get("viral_potential", "medium").lower()
    viral_scores = {"high": 2.0, "medium": 1.0, "low": 0.5}
    score += viral_scores.get(viral_potential, 1.0)
    
    # Качество заголовка с фокусом на ценность
    value_words_in_title = sum(1 for word in ["secret", "how", "why", "best", "truth", "mistake", "avoid", "key"] if word in title)
    score += value_words_in_title * 1.0
    
    # Конкретность и специфичность
    keywords = highlight.get("keywords", [])
    if len(keywords) >= 3:
        score += 2.0
    elif len(keywords) >= 2:
        score += 1.0
    
    # Бонус за наличие детального хука и кульминации
    if len(hook) > 20:
        score += 1.5
    if len(climax) > 20:
        score += 1.5
    
    # Штраф за общие фразы
    generic_phrases = ["interesting", "good", "nice", "cool", "awesome"]
    penalty = sum(0.5 for phrase in generic_phrases if phrase in all_text)
    score -= min(penalty, 2.0)
    
    return round(max(score, 0), 2)  # Минимум 0 баллов

def analyze_with_chatgpt(transcript_text: str, video_duration: float) -> Optional[Dict]:
    """Улучшенный анализ транскрипта с продвинутым алгоритмом поиска клипов"""
    try:
        # Адаптивное определение количества клипов с учетом реальности
        if video_duration <= 60:  # До 1 минуты - только лучший момент
            target_clips = 1
            min_quality_threshold = 4.0  # Очень мягкие требования для коротких видео
            logger.info(f"📹 Короткое видео ({video_duration}s) - ищем 1 лучший момент")
        elif video_duration <= 120:  # До 2 минут - максимум 2 клипа
            target_clips = 2
            min_quality_threshold = 5.0
            logger.info(f"📹 Короткое видео ({video_duration}s) - ищем до 2 клипов")
        elif video_duration <= 300:  # До 5 минут - максимум 3 клипа
            target_clips = 3
            min_quality_threshold = 6.0
        elif video_duration <= 600:  # До 10 минут - максимум 4 клипа
            target_clips = 4
            min_quality_threshold = 6.5
        elif video_duration <= 1200:  # До 20 минут - максимум 5 клипов
            target_clips = 5
            min_quality_threshold = 7.0
        elif video_duration <= 1800:  # До 30 минут - максимум 6 клипов
            target_clips = 6
            min_quality_threshold = 7.5
        else:  # Больше 30 минут - максимум 7 клипов
            target_clips = 7
            min_quality_threshold = 8.0
            
        logger.info(f"🎯 Цель: {target_clips} клипов с минимальным качеством {min_quality_threshold} баллов")
        
        # Проверяем, достаточно ли времени для запрошенного количества клипов
        min_clip_duration = Config.CLIP_MIN_DURATION
        max_possible_clips = max(1, int(video_duration / (min_clip_duration + 5)))  # +5 сек между клипами
        
        if target_clips > max_possible_clips:
            target_clips = max_possible_clips
            logger.warning(f"⚠️ Видео слишком короткое для {target_clips} клипов, скорректировано до {max_possible_clips}")
        
        # Анализируем контент для определения типа видео
        content_type = analyze_content_type(transcript_text)
        
        # Анализируем ценность контента
        value_indicators = analyze_content_value(transcript_text)
        
        # Определяем ключевые моменты в тексте
        key_moments = identify_key_moments(transcript_text)
        # Создаем специализированный промпт в зависимости от типа контента
        content_strategies = {
            'educational': """
EDUCATIONAL CONTENT STRATEGY:
- Key concepts and their explanations
- Practical examples and case studies
- Step-by-step instructions
- Important conclusions and summaries
- Answers to frequently asked questions
- Demonstrations and proofs
""",
            'entertainment': """
ENTERTAINMENT CONTENT STRATEGY:
- Funniest and brightest moments
- Unexpected twists and surprises
- Emotional peaks (laughter, surprise, delight)
- Interesting stories with climax
- Amusing dialogues and interactions
- High-energy moments
""",
            'business': """
BUSINESS CONTENT STRATEGY:
- Specific advice and strategies
- Success and failure examples
- Numbers, statistics, results
- Insights and revelations
- Practical recommendations
- Motivational moments
""",
            'personal': """
PERSONAL CONTENT STRATEGY:
- Emotional stories and experiences
- Life lessons and wisdom
- Moments of overcoming difficulties
- Personal revelations and insights
- Inspiring moments
- Genuine emotions and feelings
""",
            'tech': """
TECH CONTENT STRATEGY:
- New feature demonstrations
- Complex concepts explained simply
- Practical technology applications
- Comparisons and reviews
- Problem solutions and life hacks
- Future trends and predictions
"""
        }
        
        strategy = content_strategies.get(content_type, content_strategies['personal'])
        
        # Добавляем информацию о ценности контента в промпт
        value_context = f"""
CONTENT VALUE ANALYSIS:
- Actionable advice moments: {value_indicators.get('actionable_advice', 0)}
- Specific numbers/data: {value_indicators.get('specific_numbers', 0)}
- Personal stories: {value_indicators.get('personal_stories', 0)}
- Expert insights: {value_indicators.get('expert_insights', 0)}
- Problem solutions: {value_indicators.get('problem_solutions', 0)}
- Surprising facts: {value_indicators.get('surprising_facts', 0)}
- Practical tips: {value_indicators.get('practical_tips', 0)}

KEY MOMENTS DETECTED: {', '.join(key_moments[:10]) if key_moments else 'None detected'}

PRIORITY: Focus on moments with highest value density - where multiple value indicators overlap.
"""
        
        prompt = f"""
You are a world-class content strategist with 10+ years of experience creating viral content that gets millions of views. Your job is to find the MOST VALUABLE moments that will genuinely help, entertain, or inspire the audience.

CONTENT TYPE: {content_type.upper()}
{strategy}

{value_context}

DEEP VALUE ANALYSIS - Find moments that provide:
1. ACTIONABLE INSIGHTS: Specific advice people can immediately use
2. EMOTIONAL BREAKTHROUGHS: Moments that change how people think/feel
3. SURPRISING REVELATIONS: Information that challenges common beliefs
4. PRACTICAL SOLUTIONS: Clear answers to real problems
5. INSPIRATIONAL MOMENTS: Stories that motivate action
6. EXPERT SECRETS: Insider knowledge not commonly known
7. RELATABLE STRUGGLES: Universal experiences people connect with
8. TRANSFORMATION STORIES: Before/after moments showing change

AUDIENCE VALUE FILTERS:
- Will this moment make someone's life better?
- Does this solve a real problem people have?
- Is this information genuinely useful or just entertaining?
- Would someone save/share this with friends?
- Does this provide unique perspective or insight?
- Can viewers apply this knowledge immediately?

Transcript: {transcript_text}

PREMIUM CLIP SELECTION CRITERIA:
1. VALUE DENSITY: Maximum useful information per second
2. IMMEDIATE APPLICABILITY: Viewers can use this knowledge today
3. UNIQUE PERSPECTIVE: Information not available elsewhere
4. EMOTIONAL RESONANCE: Creates genuine connection with audience
5. PROBLEM-SOLUTION FIT: Addresses real pain points
6. SHAREABILITY FACTOR: People will want to share with others
7. MEMORABILITY: Key insights stick in viewer's mind
8. TRANSFORMATION POTENTIAL: Can genuinely improve someone's situation

ADAPTIVE QUALITY REQUIREMENTS (Video: {video_duration:.1f}s, Target: {target_clips} clips):
1. Create UP TO {target_clips} clips - prioritize QUALITY over quantity
2. Duration: {Config.CLIP_MIN_DURATION}-{Config.CLIP_MAX_DURATION} seconds (adapt to video length)
3. For SHORT videos (<2min): Focus on the SINGLE best moment if needed
4. For MEDIUM videos (2-10min): Find 2-4 distinct valuable moments
5. For LONG videos (>10min): Find multiple high-value segments
6. Each clip must provide GENUINE VALUE - not just entertainment
7. Clips must NOT overlap in time
8. Time within 0-{video_duration:.1f} seconds
9. Start with immediate value proposition, end with actionable takeaway
10. REJECT moments that are just filler or low-value content
11. If video is too short for multiple clips, create ONE exceptional clip
12. Better to have fewer HIGH-QUALITY clips than many mediocre ones

TITLE REQUIREMENTS:
- Use ONLY English language
- Maximum 3-5 words for readability
- Use engaging words: "Secret", "Truth About", "How", "Why", "Top", "Best", "Shocking"
- Avoid long sentences
- Make titles intriguing and clickable

GOOD TITLE EXAMPLES:
- "AI Success Secret"
- "Truth About Chatbots"
- "How AI Makes Money"
- "Why Everyone Fears AI"
- "Top Business Mistakes"

Return result STRICTLY in JSON format:
{{
    "highlights": [
        {{
            "start_time": 0,
            "end_time": 55,
            "title": "AI Success Secret",
            "description": "Why this moment will hook viewers and make them watch till the end",
            "hook": "What exactly in the first seconds will grab viewer attention",
            "climax": "Climactic moment or main insight of the clip",
            "viral_potential": "high",
            "emotion": "surprise",
            "keywords": ["AI", "success", "secret"],
            "best_for": ["tiktok", "instagram", "youtube_shorts"]
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
            
            # Улучшенная валидация и оптимизация клипов
            optimized_highlights = []
            for i, highlight in enumerate(highlights):
                duration = highlight["end_time"] - highlight["start_time"]
                
                # Коррекция длительности
                if duration < Config.CLIP_MIN_DURATION:
                    highlight["end_time"] = min(highlight["start_time"] + Config.CLIP_MIN_DURATION, video_duration)
                elif duration > Config.CLIP_MAX_DURATION:
                    highlight["end_time"] = highlight["start_time"] + Config.CLIP_MAX_DURATION
                
                # Добавляем метрики качества
                highlight["quality_score"] = calculate_clip_quality_score(highlight, transcript_text)
                highlight["duration"] = highlight["end_time"] - highlight["start_time"]
                
                # Устанавливаем значения по умолчанию для новых полей
                highlight.setdefault("viral_potential", "medium")
                highlight.setdefault("emotion", "neutral")
                highlight.setdefault("hook", highlight.get("title", ""))
                highlight.setdefault("climax", highlight.get("description", ""))
                highlight.setdefault("best_for", ["youtube_shorts", "tiktok"])
                
                optimized_highlights.append(highlight)
            
            # Сортируем по качеству и выбираем лучшие
            optimized_highlights.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
            
            # Адаптивная фильтрация с учетом длительности видео
            high_quality_clips = [clip for clip in optimized_highlights if clip.get("quality_score", 0) >= min_quality_threshold]
            
            if len(high_quality_clips) >= target_clips:
                highlights = high_quality_clips[:target_clips]
                logger.info(f"✅ Отобрано {len(highlights)} клипов с качеством {min_quality_threshold}+ баллов")
            elif len(high_quality_clips) > 0:
                # Если есть хотя бы несколько качественных клипов, используем их
                highlights = high_quality_clips
                logger.info(f"📊 Найдено {len(highlights)} качественных клипов из {target_clips} запрошенных")
            else:
                # Для очень коротких видео или низкокачественного контента - берем лучшие доступные
                highlights = optimized_highlights[:min(target_clips, len(optimized_highlights))]
                logger.warning(f"⚠️ Низкое качество контента, взяты {len(highlights)} лучших доступных клипов")
                    
            # Для коротких видео не добавляем fallback клипы - лучше меньше, но качественнее
            if len(highlights) < target_clips and video_duration > 300:  # Только для видео длиннее 5 минут
                logger.warning(f"ChatGPT вернул {len(highlights)} клипов вместо {target_clips} для длинного видео")
                last_end = highlights[-1]["end_time"] if highlights else 0
                clips_to_add = min(target_clips - len(highlights), 2)  # Максимум 2 дополнительных клипа
                
                for i in range(clips_to_add):
                    if last_end + Config.CLIP_MIN_DURATION + 10 <= video_duration:
                        clip_duration = min(Config.CLIP_MAX_DURATION, video_duration - last_end - 10)
                        highlights.append({
                            "start_time": last_end + 10,
                            "end_time": min(last_end + clip_duration, video_duration),
                            "title": f"Additional Moment {len(highlights) + 1}",
                            "description": "Additional valuable moment from the video",
                            "keywords": [],
                            "quality_score": min_quality_threshold - 0.5  # Чуть ниже порога
                        })
                        last_end = highlights[-1]["end_time"]
            elif len(highlights) < target_clips:
                logger.info(f"📊 Короткое видео: найдено {len(highlights)} качественных клипов из {target_clips} запрошенных - это нормально")
            # Логируем результаты анализа
            avg_quality = sum(h.get("quality_score", 0) for h in highlights) / len(highlights) if highlights else 0
            high_quality_clips = sum(1 for h in highlights if h.get("quality_score", 0) >= 7.0)
            
            logger.info(f"🎯 Анализ завершен: {len(highlights)} клипов, средняя оценка: {avg_quality:.1f}, высокого качества: {high_quality_clips}")
            
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
    clip_duration = (Config.CLIP_MIN_DURATION + Config.CLIP_MAX_DURATION) // 2  # Средняя длительность
    gap = 5  # Больший промежуток между клипами
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
            "title": f"Clip {i+1}",
            "description": "Automatically generated clip",
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
        
        # Оптимизированная команда ffmpeg для быстрой обработки
        cmd = [
            "ffmpeg", "-y",  # Перезаписывать файлы
            "-ss", str(start_time),  # Время начала (ПЕРЕД входным файлом для быстрого поиска)
            "-i", input_path,  # Входной файл
            "-t", str(end_time - start_time),  # Длительность
            "-vf", f"scale={crop_params['width']}:{crop_params['height']}:force_original_aspect_ratio=increase,crop={crop_params['width']}:{crop_params['height']}",
            "-c:v", "libx264",  # Видео кодек
            "-c:a", "aac",  # Аудио кодек
            "-preset", "veryfast",  # Быстрое кодирование (компромисс скорость/качество)
            "-crf", "26",  # Хорошее качество
            "-threads", "2",  # Два потока для ускорения
            "-avoid_negative_ts", "make_zero",  # Избегаем проблем с таймингом
            output_path
        ]
        
        # Выполняем команду с увеличенным таймаутом для длинных клипов
        clip_duration = end_time - start_time
        timeout = max(240, clip_duration * Config.FFMPEG_TIMEOUT_MULTIPLIER)  # Минимум 4 минуты или 4x длительность клипа
        logger.info(f"🎬 Нарезка клипа {clip_duration:.1f}с с таймаутом {timeout}с")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        
        if result.returncode == 0 and os.path.exists(output_path):
            logger.info(f"✅ Видео сегмент создан: {output_path}")
            return True
        else:
            logger.warning(f"⚠️ Первая попытка не удалась, пробуем упрощенную команду: {result.stderr}")
            # Fallback: упрощенная команда без обрезки
            simple_cmd = [
                "ffmpeg", "-y",
                "-ss", str(start_time),
                "-i", input_path,
                "-t", str(end_time - start_time),
                "-c", "copy",  # Копируем без перекодирования
                output_path
            ]
            try:
                simple_result = subprocess.run(simple_cmd, capture_output=True, text=True, timeout=timeout//2)
                if simple_result.returncode == 0 and os.path.exists(output_path):
                    logger.info(f"✅ Видео сегмент создан (упрощенная команда): {output_path}")
                    return True
                else:
                    logger.error(f"❌ Ошибка ffmpeg (упрощенная команда): {simple_result.stderr}")
                    return False
            except subprocess.TimeoutExpired:
                logger.error(f"❌ Таймаут даже с упрощенной командой")
                return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"❌ Таймаут при нарезке видео: {clip_duration:.1f}с клип, таймаут {timeout}с")
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
    """Подготавливает субтитры для конкретного клипа с улучшенной фильтрацией"""
    # Улучшенная фильтрация: включаем слова, которые пересекаются с временным диапазоном
    clip_words = []
    for word in transcript:
        word_start = word.get("start", 0)
        word_end = word.get("end", 0)
        
        # Включаем слово если оно хотя бы частично попадает в диапазон
        if (word_start < end_time and word_end > start_time):
            clip_words.append(word)
    
    logger.info(f"🔍 Найдено {len(clip_words)} слов в диапазоне {start_time:.1f}s - {end_time:.1f}s из {len(transcript)} общих слов")
    
    # Корректируем время относительно начала клипа
    adjusted_words = []
    for word in clip_words:
        adjusted_word = {
            **word,
            "start": word.get("start", 0) - start_time,
            "end": word.get("end", 0) - start_time
        }
        adjusted_words.append(adjusted_word)
    
    # Группируем слова в субтитры (настраиваемое количество слов)
    words_per_group = int(os.getenv("SUBTITLES_WORDS_PER_GROUP", "6"))
    subtitles = group_words_into_subtitles(adjusted_words, words_per_group=words_per_group)
    
    logger.info(f"📝 Подготовлено {len(subtitles)} субтитров для клипа ({start_time:.1f}s - {end_time:.1f}s)")
    
    return subtitles

def group_words_into_subtitles(words: List[Dict], words_per_group: int = 6) -> List[Dict]:
    """Группирует слова в субтитры с поддержкой заглавных букв и детальным логированием"""
    subtitles = []
    total_words_processed = 0
    
    # Настройка заглавных букв через переменную окружения
    use_uppercase = os.getenv("SUBTITLES_UPPERCASE", "true").lower() == "true"
    
    logger.debug(f"🔤 Группировка {len(words)} слов по {words_per_group} в группе, заглавные: {use_uppercase}")
    
    for i in range(0, len(words), words_per_group):
        group = words[i:i + words_per_group]
        
        if group:
            # Создаем копию группы для модификации
            processed_group = []
            group_words = []
            
            for word in group:
                processed_word = word.copy()
                word_text = word.get("word", "")
                
                if use_uppercase and word_text:
                    processed_word["word"] = word_text.upper()
                    group_words.append(word_text.upper())
                else:
                    group_words.append(word_text)
                
                processed_group.append(processed_word)
                total_words_processed += 1
            
            # Собираем текст субтитра
            subtitle_text = " ".join(group_words)
            
            subtitle = {
                "id": f"subtitle_{i // words_per_group}",
                "start": group[0].get("start", 0),
                "end": group[-1].get("end", 0),
                "text": subtitle_text,
                "words": processed_group  # Для караоке эффекта
            }
            subtitles.append(subtitle)
            
            logger.debug(f"📝 Субтитр {len(subtitles)}: '{subtitle_text}' ({subtitle['start']:.1f}s - {subtitle['end']:.1f}s)")
    
    logger.info(f"✅ Создано {len(subtitles)} субтитров из {total_words_processed} слов")
    return subtitles

def diagnose_transcript_issues(transcript_result: Dict) -> None:
    """Диагностирует потенциальные проблемы с транскрипцией"""
    logger.info("🔍 ДИАГНОСТИКА ТРАНСКРИПЦИИ:")
    
    # Проверяем структуру данных
    if "words" in transcript_result:
        words = transcript_result["words"]
        logger.info(f"📊 Найдено {len(words)} слов в формате word-level")
        
        # Анализируем первые 10 слов
        sample_words = words[:10]
        for i, word in enumerate(sample_words):
            word_text = word.get("word", "N/A")
            start_time = word.get("start", "N/A")
            end_time = word.get("end", "N/A")
            logger.debug(f"  Слово {i+1}: '{word_text}' ({start_time}s - {end_time}s)")
        
        # Проверяем наличие вставных слов
        filler_words = ['um', 'uh', 'yeah', 'like', 'so', 'well', 'okay', 'right']
        found_fillers = []
        for word in words:
            word_text = word.get("word", "").lower().strip()
            if word_text in filler_words:
                found_fillers.append(word_text)
        
        logger.info(f"🎤 Найдено вставных слов: {len(found_fillers)} - {list(set(found_fillers))}")
        
        # Проверяем временные метки
        words_with_time = [w for w in words if w.get("start") is not None and w.get("end") is not None]
        logger.info(f"⏰ Слов с временными метками: {len(words_with_time)}/{len(words)}")
        
        if len(words_with_time) < len(words):
            logger.warning(f"⚠️ {len(words) - len(words_with_time)} слов без временных меток!")
    
    elif "segments" in transcript_result:
        segments = transcript_result["segments"]
        logger.info(f"📊 Найдено {len(segments)} сегментов")
        
        total_words = 0
        for segment in segments:
            if "words" in segment:
                total_words += len(segment["words"])
        
        logger.info(f"📝 Общее количество слов в сегментах: {total_words}")
    
    else:
        logger.warning("⚠️ Неизвестная структура транскрипции!")
        logger.info(f"🔑 Доступные ключи: {list(transcript_result.keys())}")
    
    # Проверяем общий текст
    if "text" in transcript_result:
        text = transcript_result["text"]
        logger.info(f"📄 Общий текст: {len(text)} символов")
        logger.debug(f"📄 Начало текста: '{text[:100]}...'")
    
    logger.info("🔍 ДИАГНОСТИКА ЗАВЕРШЕНА")

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

