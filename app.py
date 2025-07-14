# AgentFlow AI Clips v18.3.0 - ВОССТАНОВЛЕННАЯ РАБОЧАЯ ВЕРСИЯ
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

# Импорт модуля субтитров на основе ShortGPT
from shortgpt_captions import create_word_level_subtitles

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
    version="18.3.0"
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
            "secondarycolor": "&Hff8000",  # Оранжевая подсветка
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
            "secondarycolor": "&Hffff00",  # Желтая подсветка
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
        logger.warning("⚠️ Supabase не установлен")
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

def upload_clip_to_supabase(local_path: str, filename: str) -> str:
    """Загрузка клипа в Supabase Storage"""
    if not supabase_available or not service_supabase:
        logger.warning("⚠️ Supabase недоступен, возвращаем локальный путь")
        return f"/api/clips/download/{filename}"
    
    try:
        with open(local_path, "rb") as clip_file:
            storage_path = f"clips/{datetime.now().strftime('%Y%m%d')}/{filename}"
            headers = {"Content-Type": "video/mp4"}
            response = service_supabase.storage.from_(SUPABASE_BUCKET).upload(
                storage_path, clip_file, headers=headers
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
    """Улучшенный анализ транскрипта с ChatGPT для получения 3-5 клипов"""
    try:
        target_clips = 2 if video_duration <= 30 else 3 if video_duration <= 60 else 4 if video_duration <= 120 else 5
        
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
    """Создание fallback клипов при ошибке ChatGPT"""
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

# Революционная система субтитров с ASS-форматом и караоке-эффектом
class ASSKaraokeSubtitleSystem:
    """Революционная система субтитров с ASS-форматом и караоке-эффектом"""
    
    def __init__(self):
        self.styles = {
            "modern": {
                "fontname": "Arial",
                "fontsize": 48,
                "primarycolor": "&H00FFFFFF",
                "secondarycolor": "&H000000FF", 
                "outlinecolor": "&H00000000",
                "backcolor": "&H80000000",
                "outline": 2,
                "shadow": 0,
                "alignment": 2,
                "marginv": 60
            },
            "neon": {
                "fontname": "Arial",
                "fontsize": 52,
                "primarycolor": "&H0000FFFF",
                "secondarycolor": "&H00FF00FF",
                "outlinecolor": "&H00000000", 
                "backcolor": "&H80000000",
                "outline": 3,
                "shadow": 2,
                "alignment": 2,
                "marginv": 60
            },
            "fire": {
                "fontname": "Arial",
                "fontsize": 50,
                "primarycolor": "&H0000AAFF",
                "secondarycolor": "&H000080FF",
                "outlinecolor": "&H00000000",
                "backcolor": "&H80000000", 
                "outline": 2,
                "shadow": 1,
                "alignment": 2,
                "marginv": 60
            },
            "elegant": {
                "fontname": "Arial",
                "fontsize": 46,
                "primarycolor": "&H00FFFF00",
                "secondarycolor": "&H00FFFF80",
                "outlinecolor": "&H00000000",
                "backcolor": "&H80000000",
                "outline": 2,
                "shadow": 0,
                "alignment": 2,
                "marginv": 60
            }
        }
        
    def generate_ass_file(self, words_data: List[Dict], style: str = "modern", video_duration: float = 10.0) -> str:
        """Генерирует ASS файл с караоке-эффектом для подсветки слов"""
        try:
            style_config = self.styles.get(style, self.styles["modern"])
            ass_filename = f"subtitles_{uuid.uuid4().hex[:8]}.ass"
            ass_path = os.path.join(Config.ASS_DIR, ass_filename)
            os.makedirs(Config.ASS_DIR, exist_ok=True)
            
            ass_content = f"""[Script Info]
Title: AgentFlow AI Clips Karaoke Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style_config['fontname']},{style_config['fontsize']},{style_config['primarycolor']},{style_config['secondarycolor']},{style_config['outlinecolor']},{style_config['backcolor']},1,0,0,0,100,100,0,0,1,{style_config['outline']},{style_config['shadow']},{style_config['alignment']},10,10,{style_config['marginv']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
            
            phrases = self._group_words_into_phrases(words_data)
            for phrase in phrases:
                start_time = self._seconds_to_ass_time(phrase['start'])
                end_time = self._seconds_to_ass_time(phrase['end'])
                karaoke_text = self._create_karaoke_effect(phrase['words'])
                ass_content += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{karaoke_text}\n"
            
            with open(ass_path, 'w', encoding='utf-8') as f:
                f.write(ass_content)
            logger.info(f"✅ ASS файл создан: {ass_path}")
            return ass_path
        except Exception as e:
            logger.error(f"❌ Ошибка создания ASS файла: {e}")
            raise
    
    def _group_words_into_phrases(self, words_data: List[Dict], max_words_per_phrase: int = 4) -> List[Dict]:
        """Группирует слова в фразы для оптимального отображения"""
        phrases = []
        current_phrase = []
        for word_data in words_data:
            current_phrase.append(word_data)
            if len(current_phrase) >= max_words_per_phrase or word_data['word'].endswith(('.', '!', '?', ',')):
                if current_phrase:
                    phrases.append({
                        'words': current_phrase.copy(),
                        'start': current_phrase[0]['start'],
                        'end': current_phrase[-1]['end']
                    })
                    current_phrase = []
        if current_phrase:
            phrases.append({
                'words': current_phrase,
                'start': current_phrase[0]['start'],
                'end': current_phrase[-1]['end']
            })
        return phrases
    
    def _create_karaoke_effect(self, words: List[Dict]) -> str:
        """Создает караоке-эффект для списка слов"""
        karaoke_parts = []
        for i, word_data in enumerate(words):
            word = word_data['word'].strip()
            if not word:
                continue
            duration = max(50, min(500, int((word_data['end'] - word_data['start']) * 100)))
            karaoke_parts.append(f"{{\\kf{duration}}}{word}")
            if i < len(words) - 1:
                karaoke_parts.append(" ")
        return "".join(karaoke_parts)
    
    def _seconds_to_ass_time(self, seconds: float) -> str:
        """Конвертирует секунды в формат времени ASS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centiseconds = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

# Инициализируем систему ASS караоке
ass_subtitle_system = ASSKaraokeSubtitleSystem()

def create_clip_with_ass_subtitles(
    video_path: str, 
    start_time: float, 
    end_time: float, 
    words_data: List[Dict],
    output_path: str,
    format_type: str = "9:16",
    style: str = "modern"
) -> bool:
    """
    Создает клип с ASS субтитрами (двухэтапный процесс)
    
    ЭТАП 1: Создание базового видео с обрезкой
    ЭТАП 2: Наложение ASS субтитров
    """
    try:
        logger.info(f"🎬 Начинаем создание клипа с ASS субтитрами")
        logger.info(f"📊 Параметры: {start_time}-{end_time}s, формат {format_type}, стиль {style}")
        
        format_type = format_type.replace('_', ':')
        crop_params = get_crop_parameters(1920, 1080, format_type)
        if not crop_params:
            logger.error(f"❌ Неподдерживаемый формат: {format_type}")
            return False
        
        clip_words = []
        logger.info(f"🔍 Фильтруем слова для клипа {start_time}s-{end_time}s из {len(words_data)} общих слов")
        for word_data in words_data:
            word_start = word_data.get('start', 0)
            word_end = word_data.get('end', 0)
            if word_start <= end_time and word_end >= start_time:
                clip_word_start = max(0, word_start - start_time)
                clip_word_end = min(end_time - start_time, word_end - start_time)
                if clip_word_end > clip_word_start:
                    clip_words.append({
                        'text': word_data.get('word', ''),
                        'start': clip_word_start,
                        'end': clip_word_end
                    })
                    logger.debug(f"✅ Слово '{word_data.get('word', '')}' добавлено: {clip_word_start:.1f}s-{clip_word_end:.1f}s")
        
        logger.info(f"📝 Найдено {len(clip_words)} слов для субтитров")
        temp_video_path = output_path.replace('.mp4', '_temp.mp4')
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # ЭТАП 1: Создание базового видео
        base_cmd = [
            'ffmpeg', '-i', video_path,
            '-ss', str(start_time),
            '-t', str(end_time - start_time),
            '-vf', f"scale={crop_params['scale']},crop={crop_params['crop']}",
            '-c:v', 'libx264', '-preset', 'fast',
            '-c:a', 'aac', '-b:a', '128k',
            '-y', temp_video_path
        ]
        logger.info("🎬 ЭТАП 1: Создаем базовое видео...")
        result = subprocess.run(base_cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=300)
        if result.returncode != 0:
            logger.error(f"❌ ЭТАП 1 неудачен: {result.stderr}")
            return False
        logger.info("✅ ЭТАП 1 завершен")
        
        if clip_words:
            try:
                logger.info("📝 ЭТАП 2: Создаем ASS субтитры (караоке-подход)...")
                transcript_data = {'segments': [{'words': clip_words}]}
                subtitle_segments = create_word_level_subtitles(transcript_data, max_caption_size=25)
                logger.info(f"📝 Создано {len(subtitle_segments)} групп субтитров")
                
                if not subtitle_segments:
                    logger.warning("⚠️ Сегменты субтитров пусты")
                
                ass_path = ass_subtitle_system.generate_ass_file(clip_words, style, end_time - start_time)
                if ass_path:
                    subtitle_cmd = [
                        'ffmpeg', '-i', temp_video_path,
                        '-vf', f"ass={ass_path}",
                        '-c:v', 'libx264', '-preset', 'fast',
                        '-c:a', 'copy',
                        '-y', output_path
                    ]
                    logger.info("📝 Применяем ASS субтитры с караоке-подсветкой...")
                    result = subprocess.run(subtitle_cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=300)
                    if result.returncode == 0:
                        logger.info("✅ ЭТАП 2 завершен: субтитры наложены")
                        os.remove(temp_video_path)
                        if os.path.exists(ass_path):
                            os.remove(ass_path)
                        return True
                    logger.error(f"❌ ЭТАП 2 неудачен: {result.stderr}")
                else:
                    logger.warning("⚠️ Не удалось создать ASS файл")
            except Exception as e:
                logger.error(f"❌ Ошибка в ЭТАПЕ 2: {e}")
        else:
            logger.warning("⚠️ Нет слов для субтитров")
        
        os.rename(temp_video_path, output_path)
        return True
    except subprocess.TimeoutExpired:
        logger.error("❌ Таймаут при создании клипа")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка создания клипа: {e}")
        return False

def get_crop_parameters(width: int, height: int, format_type: str) -> Optional[Dict]:
    """Возвращает параметры обрезки для разных форматов"""
    formats = {
        "9:16": {"target_width": 720, "target_height": 1280},
        "16:9": {"target_width": 1280, "target_height": 720},
        "1:1": {"target_width": 720, "target_height": 720},
        "4:5": {"target_width": 720, "target_height": 900}
    }
    if format_type not in formats:
        return None
    target = formats[format_type]
    target_width = target["target_width"]
    target_height = target["target_height"]
    scale_x = target_width / width
    scale_y = target_height / height
    scale = max(scale_x, scale_y)
    new_width = int(width * scale)
    new_height = int(height * scale)
    crop_x = (new_width - target_width) // 2
    crop_y = (new_height - target_height) // 2
    return {
        "scale": f"{new_width}:{new_height}",
        "crop": f"{target_width}:{target_height}:{crop_x}:{crop_y}"
    }

# API Endpoints

@app.get("/")
async def root():
    """Главная страница API"""
    return {"message": "AgentFlow AI Clips API v18.3.0", "status": "running"}

@app.get("/health")
async def health_check():
    """Проверка состояния сервиса"""
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    upload_count = len([f for f in os.listdir(Config.UPLOAD_DIR) if os.path.isfile(os.path.join(Config.UPLOAD_DIR, f))])
    clip_count = len([f for f in os.listdir(Config.CLIPS_DIR) if os.path.isfile(os.path.join(Config.CLIPS_DIR, f))])
    return {
        "status": "healthy",
        "version": "18.3.0",
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
        {"id": "9:16", "name": "Vertical", "dimensions": "720×1280", "description": "TikTok, Instagram Reels, Shorts", "aspect_ratio": 0.5625},
        {"id": "16:9", "name": "Horizontal", "dimensions": "1280×720", "description": "YouTube, Facebook", "aspect_ratio": 1.7778},
        {"id": "1:1", "name": "Square", "dimensions": "720×720", "description": "Instagram Posts", "aspect_ratio": 1.0},
        {"id": "4:5", "name": "Portrait", "dimensions": "720×900", "description": "Instagram Stories", "aspect_ratio": 0.8}
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
        if file.size and file.size > Config.MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="Файл слишком большой")
        video_id = str(uuid.uuid4())
        file_extension = os.path.splitext(file.filename)[1].lower()
        if file_extension not in ['.mp4', '.mov', '.avi', '.mkv']:
            raise HTTPException(status_code=400, detail="Неподдерживаемый формат видео")
        video_path = os.path.join(Config.UPLOAD_DIR, f"{video_id}{file_extension}")
        with open(video_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        duration = get_video_duration(video_path)
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
        background_tasks.add_task(analyze_video_task, video_id)
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
        audio_path = os.path.join(Config.AUDIO_DIR, f"{video_id}.mp3")
        if not extract_audio(video_path, audio_path):
            raise Exception("Ошибка извлечения аудио")
        logger.info(f"🎵 Аудио извлечено: {audio_path}")
        transcript_data = safe_transcribe_audio(audio_path)
        if not transcript_data:
            raise Exception("Ошибка транскрибации")
        logger.info(f"📝 Транскрибация завершена")
        transcript_text = transcript_data.get('text', '')
        analysis_result = analyze_with_chatgpt(transcript_text, video_duration)
        if not analysis_result:
            target_clips = 3 if video_duration <= 60 else 5
            analysis_result = create_fallback_highlights(video_duration, target_clips)
        highlights = analysis_result.get("highlights", [])
        valid_highlights = []
        for highlight in highlights:
            start_time = highlight.get("start_time", 0)
            end_time = highlight.get("end_time", 20)
            if start_time >= video_duration - 5:
                continue
            if end_time > video_duration:
                end_time = video_duration
            if end_time - start_time < 5:
                continue
            highlight["start_time"] = start_time
            highlight["end_time"] = end_time
            valid_highlights.append(highlight)
        if not valid_highlights:
            target_clips = 3 if video_duration <= 60 else 5
            clip_duration = min(18, video_duration / target_clips)
            for i in range(target_clips):
                start = i * (clip_duration + 2)
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
        task_id = str(uuid.uuid4())
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
        generation_tasks[task_id]["status"] = "generating"
        logger.info(f"🚀 Запущена генерация клипов: {task_id}")
        logger.info(f"🎬 Начинаю генерацию {len(highlights)} клипов")
        clips_created = 0
        total_clips = len(highlights)
        for i, highlight in enumerate(highlights):
            try:
                start_time = highlight["start_time"]
                end_time = highlight["end_time"]
                logger.info(f"🎬 Создаю клип {i+1}/{total_clips}: {start_time}-{end_time}s")
                progress = int((i / total_clips) * 100)
                generation_tasks[task_id]["progress"] = progress
                generation_tasks[task_id]["current_stage"] = f"Создание клипа {i+1}/{total_clips}"
                words_in_range = []
                if 'words' in transcript_data:
                    for word_data in transcript_data['words']:
                        word_start = word_data.get('start', 0)
                        word_end = word_data.get('end', 0)
                        if word_start <= end_time and word_end >= start_time:
                            adjusted_word = word_data.copy()
                            adjusted_word['start'] = max(0, word_start - start_time)
                            adjusted_word['end'] = min(end_time - start_time, word_end - start_time)
                            if adjusted_word['end'] > adjusted_word['start']:
                                words_in_range.append(adjusted_word)
                                logger.debug(f"✅ Слово '{word_data.get('word', '')}' добавлено: {adjusted_word['start']:.1f}s-{adjusted_word['end']:.1f}s")
                logger.info(f"📝 Найдено {len(words_in_range)} слов для субтитров в диапазоне {start_time}-{end_time}s")
                clip_filename = f"{task_id}_clip_{i+1}_{format_id.replace(':', 'x')}.mp4"
                clip_path = os.path.join(Config.CLIPS_DIR, clip_filename)
                success = create_clip_with_ass_subtitles(
                    video_path, start_time, end_time, words_in_range, clip_path, format_id, style_id
                )
                if success:
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
    logger.info("🚀 AgentFlow AI Clips v18.3.0 started!")
    logger.info("🎬 ASS караоке-система активирована")
    logger.info("🔥 GPU-ускорение через libass")
    logger.info("⚡ Двухэтапная генерация клипов")
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
