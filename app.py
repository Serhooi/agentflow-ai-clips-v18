# AgentFlow AI Clips v18.1.7 - ИСПРАВЛЕННАЯ ВЕРСИЯ
# Улучшенный анализ для 3-5 клипов + исправление Supabase

import os
import json
import uuid
import asyncio
import logging
import subprocess
import tempfile
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import psutil
import time

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import openai
from openai import OpenAI

# Supabase Storage интеграция
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
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
    description="Профессиональная система генерации коротких клипов с ASS караоке-субтитрами",
    version="18.1.7"
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
    # Основные папки
    UPLOAD_DIR = "uploads"
    AUDIO_DIR = "audio"
    CLIPS_DIR = "clips"
    ASS_DIR = "ass_subtitles"
    
    # Лимиты
    MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
    
    # Настройки очистки
    MAX_TASK_AGE = 24 * 60 * 60  # 24 часа
    CLEANUP_INTERVAL = 3600      # Очистка каждый час
    
    # ASS стили для караоке
    ASS_STYLES = {
        "modern": {
            "name": "Modern",
            "fontname": "Montserrat",
            "fontsize": 16,
            "primarycolor": "&Hffffff",  # Белый текст
            "secondarycolor": "&H00ff00",  # Зеленая подсветка караоке
            "outlinecolor": "&H000000",
            "backcolor": "&H80000000",
            "bold": -1,
            "italic": 0,
            "underline": 0,
            "strikeout": 0,
            "scalex": 100,
            "scaley": 100,
            "spacing": 0,
            "angle": 0,
            "borderstyle": 1,
            "outline": 1,
            "shadow": 0,
            "alignment": 2,
            "marginl": 10,
            "marginr": 10,
            "marginv": 60,  # Safe zone снизу
            "encoding": 1,
            "preview_colors": ["#ffffff", "#00ff00", "#000000"]
        },
        "neon": {
            "name": "Neon",
            "fontname": "Arial",
            "fontsize": 16,
            "primarycolor": "&Hffffff",
            "secondarycolor": "&Hff00ff",  # Пурпурная подсветка
            "outlinecolor": "&H000000",
            "backcolor": "&H80000000",
            "bold": -1,
            "italic": 0,
            "underline": 0,
            "strikeout": 0,
            "scalex": 100,
            "scaley": 100,
            "spacing": 0,
            "angle": 0,
            "borderstyle": 1,
            "outline": 2,
            "shadow": 0,
            "alignment": 2,
            "marginl": 10,
            "marginr": 10,
            "marginv": 60,
            "encoding": 1,
            "preview_colors": ["#ffffff", "#ff00ff", "#000000"]
        },
        "fire": {
            "name": "Fire",
            "fontname": "Impact",
            "fontsize": 16,
            "primarycolor": "&Hffffff",
            "secondarycolor": "&H0080ff",  # Оранжевая подсветка
            "outlinecolor": "&H000000",
            "backcolor": "&H80000000",
            "bold": -1,
            "italic": 0,
            "underline": 0,
            "strikeout": 0,
            "scalex": 100,
            "scaley": 100,
            "spacing": 0,
            "angle": 0,
            "borderstyle": 1,
            "outline": 2,
            "shadow": 1,
            "alignment": 2,
            "marginl": 10,
            "marginr": 10,
            "marginv": 60,
            "encoding": 1,
            "preview_colors": ["#ffffff", "#ff8000", "#000000"]
        },
        "elegant": {
            "name": "Elegant",
            "fontname": "Georgia",
            "fontsize": 16,
            "primarycolor": "&Hffffff",
            "secondarycolor": "&H00ffff",  # Желтая подсветка
            "outlinecolor": "&H000000",
            "backcolor": "&H80000000",
            "bold": 0,
            "italic": 0,
            "underline": 0,
            "strikeout": 0,
            "scalex": 100,
            "scaley": 100,
            "spacing": 0,
            "angle": 0,
            "borderstyle": 1,
            "outline": 1,
            "shadow": 0,
            "alignment": 2,
            "marginl": 10,
            "marginr": 10,
            "marginv": 60,
            "encoding": 1,
            "preview_colors": ["#ffffff", "#ffff00", "#000000"]
        }
    }

# Создание необходимых папок
for directory in [Config.UPLOAD_DIR, Config.AUDIO_DIR, Config.CLIPS_DIR, Config.ASS_DIR]:
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
        logger.warning("⚠️ Supabase не доступен, используется локальное хранение")
        return False
    
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")
        supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if not all([supabase_url, supabase_anon_key, supabase_service_key]):
            logger.warning("⚠️ Не все Supabase переменные настроены")
            return False
        
        # Основной клиент
        supabase = create_client(supabase_url, supabase_anon_key)
        
        # Service role клиент для загрузки файлов
        service_supabase = create_client(supabase_url, supabase_service_key)
        
        logger.info("✅ Supabase Storage подключен")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Supabase: {e}")
        return False

# Инициализация Supabase при запуске
supabase_available = init_supabase()

# Pydantic модели
class VideoAnalysisRequest(BaseModel):
    video_id: str

class ClipGenerationRequest(BaseModel):
    video_id: str
    format_id: str
    style_id: str = "modern"

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
    style_id: str
    status: str
    progress: int
    current_stage: Optional[str] = None
    stage_progress: Optional[int] = None

def upload_clip_to_supabase(local_path: str, filename: str) -> Optional[str]:
    """Загрузка клипа в Supabase Storage"""
    if not supabase_available or not service_supabase:
        logger.warning("⚠️ Supabase недоступен, возвращаем локальный путь")
        return f"/api/clips/download/{filename}"
    
    try:
        # Чтение файла
        with open(local_path, 'rb') as file:
            file_content = file.read()
        
        # Загрузка в Supabase Storage
        storage_path = f"clips/{datetime.now().strftime('%Y%m%d')}/{filename}"
        
        try:
            response = service_supabase.storage.from_(SUPABASE_BUCKET).upload(
                storage_path, 
                file_content,
                file_options={"content-type": "video/mp4"}
            )
            
            if response:
                # Получение публичного URL
                public_url = service_supabase.storage.from_(SUPABASE_BUCKET).get_public_url(storage_path)
                logger.info(f"✅ Клип загружен в Supabase: {storage_path}")
                return public_url
                
        except Exception as upload_error:
            logger.error(f"❌ Ошибка при загрузке: {upload_error}")
            
            # Попытка с альтернативным методом
            try:
                response = service_supabase.storage.from_(SUPABASE_BUCKET).upload(
                    storage_path, 
                    file_content
                )
                
                if response:
                    public_url = service_supabase.storage.from_(SUPABASE_BUCKET).get_public_url(storage_path)
                    logger.info(f"✅ Клип загружен в Supabase (альтернативный способ): {storage_path}")
                    return public_url
                    
            except Exception as alt_error:
                logger.error(f"❌ Альтернативная загрузка не удалась: {alt_error}")
        
    except Exception as e:
        logger.error(f"❌ Общая ошибка загрузки в Supabase: {e}")
    
    # Fallback на локальное хранение
    logger.warning("⚠️ Используется локальное хранение")
    return f"/api/clips/download/{filename}"

def get_video_duration(video_path: str) -> float:
    """Получение длительности видео"""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json', 
            '-show_format', video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data['format']['duration'])
    except Exception as e:
        logger.error(f"Ошибка получения длительности видео: {e}")
        return 60.0  # Fallback

def extract_audio(video_path: str, audio_path: str) -> bool:
    """Извлечение аудио из видео"""
    try:
        cmd = [
            'ffmpeg', '-i', video_path, '-vn', '-acodec', 'mp3', 
            '-ar', '16000', '-ac', '1', '-y', audio_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return os.path.exists(audio_path)
    except Exception as e:
        logger.error(f"Ошибка извлечения аудио: {e}")
        return False

def safe_transcribe_audio(audio_path: str) -> Optional[Dict]:
    """Безопасная транскрибация аудио с обработкой ошибок"""
    try:
        with open(audio_path, "rb") as audio_file:
            # Используем response_format="verbose_json" для получения слов с временными метками
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["word"]
            )
            
            # Проверяем разные форматы ответа
            if hasattr(transcript, 'model_dump'):
                return transcript.model_dump()
            elif hasattr(transcript, 'dict'):
                return transcript.dict()
            else:
                # Fallback для старых версий
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="json"
                )
                return transcript.model_dump() if hasattr(transcript, 'model_dump') else dict(transcript)
    except Exception as e:
        logger.error(f"Ошибка транскрибации: {e}")
        return None

def analyze_with_chatgpt(transcript_text: str, video_duration: float) -> Optional[Dict]:
    """Улучшенный анализ транскрипта с ChatGPT для получения 3-5 клипов"""
    try:
        # Определяем количество клипов на основе длительности видео
        if video_duration <= 30:
            target_clips = 2
        elif video_duration <= 60:
            target_clips = 3
        elif video_duration <= 120:
            target_clips = 4
        else:
            target_clips = 5
        
        prompt = f"""
Проанализируй этот транскрипт видео длительностью {video_duration:.1f} секунд и найди {target_clips} самых интересных и разнообразных моментов для коротких клипов.

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
        }},
        {{
            "start_time": 20,
            "end_time": 38,
            "title": "Второй момент",
            "description": "Описание второго клипа",
            "keywords": ["другие", "слова"]
        }}
    ]
}}

ВАЖНО: Отвечай ТОЛЬКО JSON, без дополнительного текста!
"""
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.7
        )
        
        content = response.choices[0].message.content.strip()
        
        # Очистка от markdown форматирования
        if content.startswith('```json'):
            content = content[7:]
        if content.endswith('```'):
            content = content[:-3]
        content = content.strip()
        
        try:
            result = json.loads(content)
            highlights = result.get("highlights", [])
            
            # Проверяем что получили нужное количество клипов
            if len(highlights) < target_clips:
                logger.warning(f"ChatGPT вернул только {len(highlights)} клипов вместо {target_clips}")
                # Дополняем до нужного количества
                while len(highlights) < target_clips:
                    last_end = highlights[-1]["end_time"] if highlights else 0
                    if last_end + 20 <= video_duration:
                        highlights.append({
                            "start_time": last_end + 2,
                            "end_time": min(last_end + 20, video_duration),
                            "title": f"Клип {len(highlights) + 1}",
                            "description": "Дополнительный клип",
                            "keywords": []
                        })
                    else:
                        break
            
            return {"highlights": highlights}
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON от ChatGPT: {e}")
            logger.error(f"Содержимое ответа: {content}")
            
            # Fallback - создаем равномерно распределенные клипы
            return create_fallback_highlights(video_duration, target_clips)
            
    except Exception as e:
        logger.error(f"Ошибка анализа с ChatGPT: {e}")
        return create_fallback_highlights(video_duration, 3)

def create_fallback_highlights(video_duration: float, target_clips: int) -> Dict:
    """Создание fallback клипов при ошибке ChatGPT"""
    highlights = []
    clip_duration = 18  # 18 секунд на клип
    gap = 2  # 2 секунды между клипами
    
    for i in range(target_clips):
        start = i * (clip_duration + gap)
        end = start + clip_duration
        
        if end > video_duration:
            # Если не помещается, делаем клип до конца видео
            end = video_duration
            start = max(0, end - clip_duration)
        
        if start >= video_duration - 5:  # Минимум 5 секунд
            break
            
        highlights.append({
            "start_time": start,
            "end_time": end,
            "title": f"Клип {i+1}",
            "description": "Автоматически созданный клип",
            "keywords": []
        })
    
    return {"highlights": highlights}

def create_ass_subtitle_file(words_data: List[Dict], style_config: Dict, output_path: str) -> bool:
    """Создание ASS файла с караоке-эффектами"""
    try:
        # Группировка слов в фразы (3-4 слова максимум)
        phrases = []
        current_phrase = []
        
        for word in words_data:
            current_phrase.append(word)
            if len(current_phrase) >= 4:  # Максимум 4 слова в фразе
                phrases.append(current_phrase)
                current_phrase = []
        
        if current_phrase:
            phrases.append(current_phrase)
        
        # Создание ASS контента
        ass_content = f"""[Script Info]
Title: AgentFlow AI Clips Karaoke
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style_config['fontname']},{style_config['fontsize']},{style_config['primarycolor']},{style_config['secondarycolor']},{style_config['outlinecolor']},{style_config['backcolor']},{style_config['bold']},{style_config['italic']},{style_config['underline']},{style_config['strikeout']},{style_config['scalex']},{style_config['scaley']},{style_config['spacing']},{style_config['angle']},{style_config['borderstyle']},{style_config['outline']},{style_config['shadow']},{style_config['alignment']},{style_config['marginl']},{style_config['marginr']},{style_config['marginv']},{style_config['encoding']}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        # Добавление событий караоке
        for phrase in phrases:
            if not phrase:
                continue
                
            start_time = phrase[0]['start']
            end_time = phrase[-1]['end']
            
            # Форматирование времени для ASS
            def format_time(seconds):
                hours = int(seconds // 3600)
                minutes = int((seconds % 3600) // 60)
                secs = seconds % 60
                return f"{hours}:{minutes:02d}:{secs:06.3f}"
            
            start_ass = format_time(start_time)
            end_ass = format_time(end_time)
            
            # Создание караоке-текста
            karaoke_text = ""
            for i, word in enumerate(phrase):
                word_duration = (word['end'] - word['start']) * 100  # В сантисекундах
                karaoke_text += f"{{\\k{int(word_duration)}}}{word['word']}"
                if i < len(phrase) - 1:
                    karaoke_text += " "
            
            ass_content += f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{karaoke_text}\n"
        
        # Сохранение файла
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка создания ASS файла: {e}")
        return False

def create_clip_with_ass_subtitles(video_path: str, start_time: float, end_time: float, 
                                 format_id: str, ass_file: str, output_path: str) -> bool:
    """Создание клипа с ASS субтитрами через двухэтапный процесс"""
    try:
        # Нормализация format_id (поддержка обоих форматов)
        format_id = format_id.replace('_', ':')  # Конвертируем 16_9 → 16:9
        
        # Определение размеров для разных форматов
        format_sizes = {
            "9:16": "720:1280",
            "16:9": "1280:720", 
            "1:1": "720:720",
            "4:5": "720:900"
        }
        
        if format_id not in format_sizes:
            raise ValueError(f"Неподдерживаемый формат: {format_id}")
        
        size = format_sizes[format_id]
        
        # Этап 1: Создание базового клипа
        temp_clip = output_path.replace('.mp4', '_temp.mp4')
        
        cmd1 = [
            'ffmpeg', '-i', video_path,
            '-ss', str(start_time),
            '-t', str(end_time - start_time),
            '-vf', f'scale={size}:force_original_aspect_ratio=increase,crop={size}',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k',
            '-y', temp_clip
        ]
        
        result1 = subprocess.run(cmd1, capture_output=True, text=True, check=True)
        
        if not os.path.exists(temp_clip):
            raise Exception("Не удалось создать базовый клип")
        
        # Этап 2: Добавление ASS субтитров
        cmd2 = [
            'ffmpeg', '-i', temp_clip,
            '-vf', f'ass={ass_file}',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'copy',
            '-y', output_path
        ]
        
        result2 = subprocess.run(cmd2, capture_output=True, text=True, check=True)
        
        # Очистка временного файла
        if os.path.exists(temp_clip):
            os.remove(temp_clip)
        
        return os.path.exists(output_path)
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка FFmpeg: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Ошибка создания клипа: {e}")
        return False

# API Endpoints

@app.get("/")
async def root():
    """Главная страница API"""
    return {"message": "AgentFlow AI Clips API v18.1.7", "status": "running"}

@app.get("/health")
async def health_check():
    """Проверка состояния сервиса"""
    # Проверка системных ресурсов
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # Подсчет файлов
    upload_count = len([f for f in os.listdir(Config.UPLOAD_DIR) if os.path.isfile(os.path.join(Config.UPLOAD_DIR, f))])
    clip_count = len([f for f in os.listdir(Config.CLIPS_DIR) if os.path.isfile(os.path.join(Config.CLIPS_DIR, f))])
    
    return {
        "status": "healthy",
        "version": "18.1.7",
        "timestamp": datetime.now().isoformat(),
        "system": {
            "memory_usage": f"{memory.percent}%",
            "disk_usage": f"{disk.percent}%",
            "uploads": upload_count,
            "clips": clip_count
        },
        "services": {
            "openai": "connected" if openai_api_key else "disconnected",
            "supabase": "connected" if supabase_available else "disconnected"
        }
    }

@app.get("/api/formats")
async def get_formats():
    """Получение доступных форматов"""
    formats = [
        {
            "id": "9:16",
            "name": "Vertical",
            "dimensions": "720×1280",
            "description": "TikTok, Instagram Reels, Shorts",
            "aspect_ratio": 0.5625
        },
        {
            "id": "16:9", 
            "name": "Horizontal",
            "dimensions": "1280×720",
            "description": "YouTube, Facebook",
            "aspect_ratio": 1.7778
        },
        {
            "id": "1:1",
            "name": "Square", 
            "dimensions": "720×720",
            "description": "Instagram Posts",
            "aspect_ratio": 1.0
        },
        {
            "id": "4:5",
            "name": "Portrait",
            "dimensions": "720×900", 
            "description": "Instagram Stories",
            "aspect_ratio": 0.8
        }
    ]
    return {"formats": formats}

@app.get("/api/styles")
async def get_styles():
    """Получение доступных стилей субтитров"""
    styles = []
    for style_id, config in Config.ASS_STYLES.items():
        styles.append({
            "id": style_id,
            "name": config["name"],
            "preview_colors": config["preview_colors"],
            "font": config["fontname"]
        })
    return {"styles": styles}

@app.post("/api/videos/upload")
async def upload_video(file: UploadFile = File(...)):
    """Загрузка видео файла"""
    try:
        # Проверка размера файла
        if file.size and file.size > Config.MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="Файл слишком большой")
        
        # Генерация уникального ID
        video_id = str(uuid.uuid4())
        
        # Сохранение файла
        file_extension = os.path.splitext(file.filename)[1].lower()
        if file_extension not in ['.mp4', '.mov', '.avi', '.mkv']:
            raise HTTPException(status_code=400, detail="Неподдерживаемый формат видео")
        
        video_path = os.path.join(Config.UPLOAD_DIR, f"{video_id}{file_extension}")
        
        with open(video_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Получение информации о видео
        duration = get_video_duration(video_path)
        
        # Сохранение информации о задаче
        analysis_tasks[video_id] = {
            "video_id": video_id,
            "filename": file.filename,
            "video_path": video_path,
            "duration": duration,
            "size": len(content),
            "status": "uploaded",
            "upload_time": datetime.now().isoformat()
        }
        
        logger.info(f"📁 Получен файл: {file.filename} ({len(content)/1024/1024:.1f} MB)")
        logger.info(f"✅ Видео загружено: {video_id}, длительность: {duration:.1f}s")
        
        return {
            "video_id": video_id,
            "filename": file.filename,
            "duration": duration,
            "size": len(content),
            "upload_time": analysis_tasks[video_id]["upload_time"],
            "status": "uploaded"
        }
    except Exception as e:
        logger.error(f"Ошибка загрузки видео: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/videos/analyze")
async def analyze_video(request: VideoAnalysisRequest, background_tasks: BackgroundTasks):
    """Анализ видео для выделения ключевых моментов"""
    try:
        video_id = request.video_id
        
        if video_id not in analysis_tasks:
            raise HTTPException(status_code=404, detail="Видео не найдено")
        
        # Запуск анализа в фоне
        background_tasks.add_task(analyze_video_task, video_id)
        
        # Обновление статуса
        analysis_tasks[video_id]["status"] = "analyzing"
        
        return {"message": "Анализ запущен", "video_id": video_id}
    except Exception as e:
        logger.error(f"Ошибка запуска анализа: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def analyze_video_task(video_id: str):
    """Фоновая задача анализа видео"""
    try:
        analysis_task = analysis_tasks[video_id]
        video_path = analysis_task["video_path"]
        video_duration = analysis_task.get("duration", 60)
        
        logger.info(f"🔍 Начинаю анализ видео: {video_id}")
        
        # Извлечение аудио
        audio_path = os.path.join(Config.AUDIO_DIR, f"{video_id}.mp3")
        if not extract_audio(video_path, audio_path):
            raise Exception("Ошибка извлечения аудио")
        
        logger.info(f"🎵 Аудио извлечено: {audio_path}")
        
        # Транскрибация
        transcript_data = safe_transcribe_audio(audio_path)
        if not transcript_data:
            raise Exception("Ошибка транскрибации")
        
        logger.info(f"📝 Транскрибация завершена")
        
        # Анализ с ChatGPT (передаем длительность видео)
        transcript_text = transcript_data.get('text', '')
        analysis_result = analyze_with_chatgpt(transcript_text, video_duration)
        
        if not analysis_result:
            # Fallback - создаем клипы автоматически
            target_clips = 3 if video_duration <= 60 else 5
            analysis_result = create_fallback_highlights(video_duration, target_clips)
        
        highlights = analysis_result.get("highlights", [])
        
        # Фильтрация и корректировка highlights
        valid_highlights = []
        for highlight in highlights:
            start_time = highlight.get("start_time", 0)
            end_time = highlight.get("end_time", 20)
            
            # Ограничиваем временные рамки длительностью видео
            if start_time >= video_duration - 5:  # Минимум 5 секунд до конца
                continue
                
            if end_time > video_duration:
                end_time = video_duration
            
            if end_time - start_time < 5:  # Минимум 5 секунд клип
                continue
                
            highlight["start_time"] = start_time
            highlight["end_time"] = end_time
            valid_highlights.append(highlight)
        
        # Если все еще нет валидных highlights, создаем принудительно
        if not valid_highlights:
            target_clips = 3 if video_duration <= 60 else 5
            clip_duration = min(18, video_duration / target_clips)
            
            for i in range(target_clips):
                start = i * (clip_duration + 2)  # 2 секунды между клипами
                end = start + clip_duration
                
                if end > video_duration:
                    end = video_duration
                    start = max(0, end - clip_duration)
                
                if start >= video_duration - 5:
                    break
                    
                valid_highlights.append({
                    "start_time": start,
                    "end_time": end,
                    "title": f"Клип {i+1}",
                    "description": "Автоматически созданный клип",
                    "keywords": []
                })
        
        # Обновление результатов
        analysis_tasks[video_id].update({
            "status": "completed",
            "transcript": transcript_data,
            "analysis": {"highlights": valid_highlights},
            "completed_at": datetime.now().isoformat()
        })
        
        logger.info(f"✅ Анализ завершен: {video_id}, найдено {len(valid_highlights)} highlights")
        
    except Exception as e:
        logger.error(f"❌ Ошибка анализа видео {video_id}: {e}")
        analysis_tasks[video_id].update({
            "status": "error",
            "error": str(e),
            "completed_at": datetime.now().isoformat()
        })

@app.get("/api/videos/{video_id}/status")
async def get_video_status(video_id: str):
    """Получение статуса анализа видео"""
    if video_id not in analysis_tasks:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    
    task = analysis_tasks[video_id]
    
    response = {
        "video_id": video_id,
        "status": task["status"],
        "filename": task.get("filename"),
        "duration": task.get("duration"),
        "upload_time": task.get("upload_time")
    }
    
    if task["status"] == "completed":
        highlights = task.get("analysis", {}).get("highlights", [])
        response["highlights"] = highlights
        response["highlights_count"] = len(highlights)
    
    if task["status"] == "error":
        response["error"] = task.get("error")
    
    return response

@app.post("/api/clips/generate")
async def generate_clips(request: ClipGenerationRequest, background_tasks: BackgroundTasks):
    """Генерация клипов с субтитрами"""
    try:
        video_id = request.video_id
        format_id = request.format_id
        style_id = request.style_id
        
        if video_id not in analysis_tasks:
            raise HTTPException(status_code=404, detail="Видео не найдено")
        
        analysis_task = analysis_tasks[video_id]
        if analysis_task["status"] != "completed":
            raise HTTPException(status_code=400, detail="Анализ видео не завершен")
        
        # Генерация уникального ID задачи
        task_id = str(uuid.uuid4())
        
        # Сохранение информации о задаче генерации
        generation_tasks[task_id] = {
            "task_id": task_id,
            "video_id": video_id,
            "format_id": format_id,
            "style_id": style_id,
            "status": "pending",
            "progress": 0,
            "clips": [],
            "created_at": datetime.now().isoformat()
        }
        
        # Запуск генерации в фоне
        background_tasks.add_task(generate_clips_task, task_id)
        
        logger.info(f"🚀 Запущена генерация клипов: {task_id}")
        
        return {
            "task_id": task_id,
            "message": "Генерация клипов запущена",
            "video_id": video_id,
            "format_id": format_id,
            "style_id": style_id
        }
        
    except Exception as e:
        logger.error(f"Ошибка запуска генерации клипов: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def generate_clips_task(task_id: str):
    """Фоновая задача генерации клипов"""
    try:
        task = generation_tasks[task_id]
        video_id = task["video_id"]
        format_id = task["format_id"]
        style_id = task["style_id"]
        
        analysis_task = analysis_tasks[video_id]
        video_path = analysis_task["video_path"]
        highlights = analysis_task["analysis"]["highlights"]
        transcript_data = analysis_task.get("transcript", {})
        
        # Обновление статуса
        generation_tasks[task_id]["status"] = "generating"
        
        logger.info(f"🎬 Начинаю генерацию {len(highlights)} клипов")
        
        clips_created = 0
        total_clips = len(highlights)
        
        for i, highlight in enumerate(highlights):
            try:
                start_time = highlight["start_time"]
                end_time = highlight["end_time"]
                
                logger.info(f"🎬 Создаю клип {i+1}/{total_clips}: {start_time}-{end_time}s")
                
                # Обновление прогресса
                progress = int((i / total_clips) * 100)
                generation_tasks[task_id]["progress"] = progress
                generation_tasks[task_id]["current_stage"] = f"Создание клипа {i+1}/{total_clips}"
                
                # Получение слов для субтитров в диапазоне времени
                words_in_range = []
                if 'words' in transcript_data:
                    for word_data in transcript_data['words']:
                        word_start = word_data.get('start', 0)
                        word_end = word_data.get('end', 0)
                        
                        # Проверяем пересечение с диапазоном клипа
                        if word_start < end_time and word_end > start_time:
                            # Корректируем время относительно начала клипа
                            adjusted_word = word_data.copy()
                            adjusted_word['start'] = max(0, word_start - start_time)
                            adjusted_word['end'] = min(end_time - start_time, word_end - start_time)
                            words_in_range.append(adjusted_word)
                
                logger.info(f"📝 Найдено {len(words_in_range)} слов для субтитров")
                
                # Создание ASS файла
                style_config = Config.ASS_STYLES.get(style_id, Config.ASS_STYLES["modern"])
                ass_filename = f"{task_id}_clip_{i+1}.ass"
                ass_path = os.path.join(Config.ASS_DIR, ass_filename)
                
                if words_in_range:
                    create_ass_subtitle_file(words_in_range, style_config, ass_path)
                else:
                    # Создаем пустой ASS файл если нет слов
                    with open(ass_path, 'w', encoding='utf-8') as f:
                        f.write("""[Script Info]
Title: Empty Subtitles
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,16,&Hffffff,&H00ff00,&H000000,&H80000000,-1,0,0,0,100,100,0,0,1,1,0,2,10,10,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""")
                
                # Создание клипа
                clip_filename = f"{task_id}_clip_{i+1}_{format_id.replace(':', 'x')}.mp4"
                clip_path = os.path.join(Config.CLIPS_DIR, clip_filename)
                
                success = create_clip_with_ass_subtitles(
                    video_path, start_time, end_time, format_id, ass_path, clip_path
                )
                
                if success:
                    # Загрузка клипа в Supabase Storage
                    supabase_url = upload_clip_to_supabase(clip_path, clip_filename)
                    
                    clip_info = {
                        "id": f"{task_id}_clip_{i+1}",
                        "title": highlight.get("title", f"Клип {i+1}"),
                        "description": highlight.get("description", ""),
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration": end_time - start_time,
                        "filename": clip_filename,
                        "download_url": supabase_url,
                        "format": format_id,
                        "style": style_id,
                        "size": os.path.getsize(clip_path) if os.path.exists(clip_path) else 0
                    }
                    
                    generation_tasks[task_id]["clips"].append(clip_info)
                    clips_created += 1
                    
                    logger.info(f"✅ Клип {i+1} создан: {clip_filename}, размер: {clip_info['size']} байт")
                else:
                    logger.error(f"❌ Ошибка создания клипа {i+1}")
                
            except Exception as clip_error:
                logger.error(f"❌ Ошибка создания клипа {i+1}: {clip_error}")
                continue
        
        # Завершение генерации
        generation_tasks[task_id].update({
            "status": "completed",
            "progress": 100,
            "current_stage": "Завершено",
            "clips_created": clips_created,
            "completed_at": datetime.now().isoformat()
        })
        
        logger.info(f"🎉 Генерация завершена: {task_id}, создано {clips_created} клипов")
        
    except Exception as e:
        logger.error(f"❌ Ошибка генерации клипов {task_id}: {e}")
        generation_tasks[task_id].update({
            "status": "error",
            "error": str(e),
            "completed_at": datetime.now().isoformat()
        })

@app.get("/api/clips/generation/{task_id}/status")
async def get_generation_status(task_id: str):
    """Получение статуса генерации клипов"""
    if task_id not in generation_tasks:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    task = generation_tasks[task_id]
    
    response = {
        "task_id": task_id,
        "status": task["status"],
        "progress": task.get("progress", 0),
        "current_stage": task.get("current_stage"),
        "clips_created": len(task.get("clips", [])),
        "created_at": task.get("created_at")
    }
    
    if task["status"] == "completed":
        response["clips"] = task.get("clips", [])
        response["completed_at"] = task.get("completed_at")
    
    if task["status"] == "error":
        response["error"] = task.get("error")
    
    return response

@app.get("/api/clips/download/{filename}")
async def download_clip(filename: str):
    """Скачивание клипа (fallback для локального хранения)"""
    file_path = os.path.join(Config.CLIPS_DIR, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=filename
    )

# Запуск приложения
if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 AgentFlow AI Clips v18.1.7 started!")
    logger.info("🎬 ASS караоке-система активирована")
    logger.info("🔥 GPU-ускорение через libass")
    logger.info("⚡ Двухэтапная генерация клипов")
    
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

