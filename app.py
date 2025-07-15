# AgentFlow AI Clips v18.5.6 - Интеграция Remotion для анимированных субтитров
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

# Supabase Storage интеграция (опционально)
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger = logging.getLogger("app")
    logger.warning("Supabase не установлен")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("app")

# Инициализация FastAPI
app = FastAPI(
    title="AgentFlow AI Clips API",
    description="Система генерации клипов с анимированными субтитрами через Remotion",
    version="18.5.6"
)

# CORS настройки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Конфигурация
class Config:
    UPLOAD_DIR = "uploads"
    AUDIO_DIR = "audio"
    CLIPS_DIR = "clips"
    REMOTION_DIR = "remotion"
    MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
    MAX_TASK_AGE = 24 * 60 * 60  # 24 часа
    CLEANUP_INTERVAL = 3600  # Очистка каждый час
    FPS = 30  # FPS для Remotion

# Создание необходимых папок
for directory in [Config.UPLOAD_DIR, Config.AUDIO_DIR, Config.CLIPS_DIR, Config.REMOTION_DIR]:
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
    """Извлечение аудио из видео"""
    try:
        cmd = ['ffmpeg', '-i', video_path, '-vn', '-acodec', 'mp3', '-ar', '16000', '-ac', '1', '-y', audio_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return os.path.exists(audio_path)
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

# СТАРЫЕ ФУНКЦИИ REMOTION - ЗАКОММЕНТИРОВАНЫ ДЛЯ ФРОНТЕНД ПОДХОДА
# def render_clip_with_remotion(video_path: str, words: List[Dict], start_time: float, end_time: float, output_path: str, format_type: str) -> bool:
#     """Рендер клипа с анимированными субтитрами через Remotion"""
#     # Функция закомментирована - теперь субтитры накладываются на фронтенде

# async def generate_clips_task(task_id: str):
#     """Фоновая задача генерации клипов"""  
#     # Функция закомментирована - теперь клипы генерируются на фронтенде


# Запуск приложения
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"🚀 AgentFlow AI Clips v18.6.2 started!")
    logger.info(f"🎬 Фронтенд подход активирован - субтитры накладываются на клиенте")
    uvicorn.run(app, host="0.0.0.0", port=port)

