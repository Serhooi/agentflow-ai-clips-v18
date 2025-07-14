# AgentFlow AI Clips v18.3.0 - ПОЛНАЯ ВЕРСIA С ОПТИМИЗАЦИЕЙ
# Разработано для генерации коротких клипов с ASS субтитрами в стиле Opus
# Оптимизировано для Render с учетом памяти и скорости обработки
# Адаптировано для поддержки множества пользователей с очередью задач
# Текущая дата: 08:42 PM EDT, 14 июля 2025

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
from collections import deque

# Импорт модуля субтитров на основе ShortGPT
from shortgpt_captions import create_word_level_subtitles

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import openai
from openai import OpenAI

# Попытка импорта Supabase с обработкой ошибок
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger = logging.getLogger("app")
    logger.warning("Модуль Supabase не установлен, локальное хранение будет использовано")

# Настройка детального логирования для диагностики
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("agentflow.log")
    ]
)
logger = logging.getLogger("app")

# Инициализация FastAPI с подробной конфигурацией
app = FastAPI(
    title="AgentFlow AI Clips API",
    description="Профессиональная система генерации коротких видео клипов с поддержкой ASS субтитров. Версия 18.3.0.",
    version="18.3.0",
    contact={
        "name": "Support Team",
        "email": "support@x.ai"
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT"
    }
)

# Настройка CORS для поддержки всех источников
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Основной класс конфигурации с расширенными настройками
class Config:
    """Класс конфигурации для управления директориями, лимитами и стилями"""
    
    # Директории для хранения данных
    UPLOAD_DIR = "uploads"
    AUDIO_DIR = "audio"
    CLIPS_DIR = "clips"
    ASS_DIR = "ass_subtitles"
    
    # Лимиты ресурсов
    MAX_FILE_SIZE = 200 * 1024 * 1024  # Ограничение 200 MB для экономии памяти
    MAX_TASK_AGE = 24 * 60 * 60        # Удаление задач старше 24 часов
    CLEANUP_INTERVAL = 3600            # Очистка каждые 60 минут
    
    # Расширенные стили для субтитров
    ASS_STYLES = {
        "opus": {
            "name": "Opus",
            "fontname": "Montserrat-Bold",
            "fontsize": 45,
            "primarycolor": "&HFFFFFF",
            "secondarycolor": "&H00FF00",
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
            "marginl": 100,
            "marginr": 100,
            "marginv": 1700,
            "encoding": 1,
            "preview_colors": ["#FFFFFF", "#00FF00", "#000000"]
        },
        "modern": {
            "name": "Modern",
            "fontname": "Montserrat-Bold",
            "fontsize": 40,
            "primarycolor": "&HFFFFFF",
            "secondarycolor": "&H00FF00",
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
            "marginv": 80,
            "encoding": 1,
            "preview_colors": ["#FFFFFF", "#00FF00", "#000000"]
        },
        "neon": {
            "name": "Neon",
            "fontname": "Arial",
            "fontsize": 40,
            "primarycolor": "&HFFFFFF",
            "secondarycolor": "&HFF00FF",
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
            "outline": 3,
            "shadow": 2,
            "alignment": 2,
            "marginl": 10,
            "marginr": 10,
            "marginv": 80,
            "encoding": 1,
            "preview_colors": ["#FFFFFF", "#FF00FF", "#000000"]
        },
        "fire": {
            "name": "Fire",
            "fontname": "Impact",
            "fontsize": 40,
            "primarycolor": "&HFFFFFF",
            "secondarycolor": "&HFF8000",
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
            "marginv": 80,
            "encoding": 1,
            "preview_colors": ["#FFFFFF", "#FF8000", "#000000"]
        },
        "elegant": {
            "name": "Elegant",
            "fontname": "Georgia",
            "fontsize": 40,
            "primarycolor": "&HFFFFFF",
            "secondarycolor": "&HFFFF00",
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
            "marginv": 80,
            "encoding": 1,
            "preview_colors": ["#FFFFFF", "#FFFF00", "#000000"]
        },
        "classic": {
            "name": "Classic",
            "fontname": "Times New Roman",
            "fontsize": 40,
            "primarycolor": "&HFFFFFF",
            "secondarycolor": "&H00FF00",
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
            "marginv": 80,
            "encoding": 1,
            "preview_colors": ["#FFFFFF", "#00FF00", "#000000"]
        },
        "vintage": {
            "name": "Vintage",
            "fontname": "Courier",
            "fontsize": 40,
            "primarycolor": "&HFFD700",
            "secondarycolor": "&HADFF2F",
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
            "marginv": 80,
            "encoding": 1,
            "preview_colors": ["#FFD700", "#ADFF2F", "#000000"]
        },
        "retro": {
            "name": "Retro",
            "fontname": "Courier New",
            "fontsize": 40,
            "primarycolor": "&HFFFF00",
            "secondarycolor": "&HFF00FF",
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
            "marginv": 80,
            "encoding": 1,
            "preview_colors": ["#FFFF00", "#FF00FF", "#000000"]
        },
        "cyber": {
            "name": "Cyber",
            "fontname": "Arial Narrow",
            "fontsize": 40,
            "primarycolor": "&H00FFFF",
            "secondarycolor": "&HFF0000",
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
            "marginv": 80,
            "encoding": 1,
            "preview_colors": ["#00FFFF", "#FF0000", "#000000"]
        }
    }

# Создание необходимых директорий с проверкой
for directory in [Config.UPLOAD_DIR, Config.AUDIO_DIR, Config.CLIPS_DIR, Config.ASS_DIR]:
    os.makedirs(directory, exist_ok=True)
    logger.debug(f"Директория создана или проверена: {directory}")

# Глобальные переменные с инициализацией
analysis_tasks = {}  # Хранит задачи анализа видео
generation_tasks = {}  # Хранит задачи генерации клипов
task_queue = deque(maxlen=1)  # Очередь для обработки одной задачи
cache = {}  # Кэш для хранения результатов транскрибации

# Инициализация OpenAI с проверкой ключа
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    logger.error("❌ Переменная OPENAI_API_KEY не найдена в окружении")
    raise ValueError("OPENAI_API_KEY обязателен для работы")
client = OpenAI(api_key=openai_api_key)
logger.info("✅ Клиент OpenAI успешно инициализирован")

# Инициализация Supabase с подробной логикой
supabase = None
service_supabase = None
SUPABASE_BUCKET = "video-results"

def init_supabase() -> bool:
    """Инициализация клиентов Supabase с обработкой ошибок"""
    global supabase, service_supabase
    if not SUPABASE_AVAILABLE:
        logger.warning("⚠️ Модуль Supabase не доступен, переход на локальное хранение")
        return False
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")
        supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not all([supabase_url, supabase_anon_key, supabase_service_key]):
            logger.warning("⚠️ Не все переменные Supabase настроены, локальное хранение активировано")
            return False
        supabase = create_client(supabase_url, supabase_anon_key)
        service_supabase = create_client(supabase_url, supabase_service_key)
        logger.info("✅ Подключение к Supabase Storage успешно установлено")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Supabase: {str(e)}")
        return False

supabase_available = init_supabase()

# Модели Pydantic для валидации запросов
class VideoAnalysisRequest(BaseModel):
    """Модель запроса для анализа видео"""
    video_id: str

class ClipGenerationRequest(BaseModel):
    """Модель запроса для генерации клипов"""
    video_id: str
    format_id: str
    style_id: str = "opus"

class VideoInfo(BaseModel):
    """Модель информации о видео"""
    id: str
    filename: str
    duration: float
    size: int
    status: str
    upload_time: str

class ClipInfo(BaseModel):
    """Модель информации о клипе"""
    id: str
    video_id: str
    format_id: str
    style_id: str
    status: str
    progress: int
    current_stage: Optional[str] = None
    stage_progress: Optional[int] = None

# Утилиты для работы с видео и аудио
def upload_clip_to_supabase(local_path: str, filename: str) -> Optional[str]:
    """Загрузка клипа в Supabase Storage с fallback на локальное хранение"""
    if not supabase_available or not service_supabase:
        logger.warning("⚠️ Supabase недоступен, используется локальный путь")
        return f"/api/clips/download/{filename}"
    try:
        with open(local_path, 'rb') as file:
            file_content = file.read()
        storage_path = f"clips/{datetime.now().strftime('%Y%m%d')}/{filename}"
        response = service_supabase.storage.from_(SUPABASE_BUCKET).upload(storage_path, file_content)
        if response:
            public_url = service_supabase.storage.from_(SUPABASE_BUCKET).get_public_url(storage_path)
            logger.info(f"✅ Клип загружен в Supabase: {storage_path}")
            return public_url
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки в Supabase: {str(e)}")
    logger.warning("⚠️ Возврат к локальному хранению из-за ошибки")
    return f"/api/clips/download/{filename}"

def get_video_duration(video_path: str) -> float:
    """Получение длительности видео с использованием ffprobe"""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data['format']['duration'])
    except Exception as e:
        logger.error(f"❌ Ошибка получения длительности видео: {str(e)}")
        return 60.0  # Значение по умолчанию

def ffmpeg_available_codecs() -> List[str]:
    """Проверка доступных кодеков FFmpeg для GPU-ускорения"""
    try:
        result = subprocess.run(['ffmpeg', '-codecs'], capture_output=True, text=True)
        return [line.split()[1] for line in result.stdout.splitlines() if 'h264_nvenc' in line or 'hevc_nvenc' in line]
    except Exception as e:
        logger.warning(f"⚠️ Ошибка проверки кодеков FFmpeg: {str(e)}")
        return []

def extract_audio(video_path: str, audio_path: str, start_time: float = 0, duration: float = None) -> bool:
    """Извлечение аудио из видео с поддержкой обрезки и детальной логикой"""
    try:
        cmd = [
            'ffmpeg', '-i', video_path, '-vn', '-acodec', 'mp3',
            '-ar', '16000', '-ac', '1', '-y', audio_path
        ]
        if start_time:
            cmd.extend(['-ss', str(start_time)])
        if duration:
            cmd.extend(['-t', str(duration)])
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return os.path.exists(audio_path)
    except subprocess.CalledProcessError as cpe:
        logger.error(f"❌ Ошибка вызова FFmpeg для аудио: {cpe.stderr}")
        return False
    except Exception as e:
        logger.error(f"❌ Общая ошибка извлечения аудио: {str(e)}")
        return False

def safe_transcribe_audio(audio_path: str) -> Optional[Dict]:
    """Безопасная транскрибация аудио с использованием кэша и повторными попытками"""
    cache_key = f"transcribe_{hash(open(audio_path, 'rb').read())}"
    if cache_key in cache:
        logger.info("📦 Использование кэшированной транскрибации")
        return cache[cache_key]
    try:
        with open(audio_path, "rb") as audio_file:
            for attempt in range(3):  # Три попытки
                try:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        response_format="verbose_json",
                        timestamp_granularities=["word"]
                    )
                    result = transcript.model_dump() if hasattr(transcript, 'model_dump') else dict(transcript)
                    cache[cache_key] = result
                    logger.info("✅ Транскрибация завершена и сохранена в кэш")
                    return result
                except openai.RateLimitError:
                    logger.warning(f"⚠️ Ограничение скорости OpenAI, попытка {attempt + 1}/3")
                    time.sleep(2 ** attempt)  # Экспоненциальное ожидание
                except Exception as e:
                    logger.error(f"❌ Ошибка транскрибации (попытка {attempt + 1}): {str(e)}")
                    time.sleep(1)
        return None
    except Exception as e:
        logger.error(f"❌ Критическая ошибка транскрибации: {str(e)}")
        return None

def analyze_with_chatgpt(transcript_text: str, video_duration: float) -> Optional[Dict]:
    """Анализ транскрипта с ChatGPT для выделения клипов с подробной логикой"""
    try:
        target_clips = 2 if video_duration <= 30 else 3 if video_duration <= 60 else 4
        prompt = f"""
Проанализируй транскрипт видео длительностью {video_duration:.1f} секунд.
Найди {target_clips} самых интересных моментов для клипов (15-20 секунд, не пересекаются).
Верни JSON с ключом 'highlights' и массивом объектов вида:
{{
    "start_time": float,
    "end_time": float,
    "title": str,
    "description": str
}}
Убедись, что моменты содержат ключевые фразы и избегают тишины.
"""
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.7
        )
        content = response.choices[0].message.content.strip()
        if content.startswith('```json'):
            content = content[7:-3]
        return json.loads(content)
    except json.JSONDecodeError as jde:
        logger.error(f"❌ Ошибка декодирования JSON: {str(jde)}")
        return create_fallback_highlights(video_duration, 3)
    except Exception as e:
        logger.error(f"❌ Ошибка анализа с ChatGPT: {str(e)}")
        return create_fallback_highlights(video_duration, 3)

def create_fallback_highlights(video_duration: float, target_clips: int) -> Dict:
    """Создание запасных клипов при ошибке анализа с детальной логикой"""
    highlights = []
    clip_duration = 18
    gap = 2
    for i in range(target_clips):
        start = i * (clip_duration + gap)
        end = min(start + clip_duration, video_duration)
        if start >= video_duration - 5:
            break
        highlights.append({
            "start_time": start,
            "end_time": end,
            "title": f"Клип {i+1}",
            "description": "Автоматически сгенерированный клип на основе равномерного разделения"
        })
    return {"highlights": highlights}

# Система субтитров с поддержкой эффекта увеличения и смены цвета
class ASSKaraokeSubtitleSystem:
    """Класс для генерации ASS-файлов с эффектом увеличения и смены цвета слова"""
    
    def __init__(self):
        self.styles = {
            "opus": {
                "fontname": "Montserrat-Bold",
                "fontsize": 45,
                "primarycolor": "&HFFFFFF",
                "secondarycolor": "&H00FF00",
                "outlinecolor": "&H000000",
                "backcolor": "&H80000000",
                "outline": 2,
                "shadow": 1,
                "alignment": 2,
                "marginl": 100,
                "marginr": 100,
                "marginv": 1700,
                "borderstyle": 1,
                "scalex": 100,
                "scaley": 100,
                "spacing": 0,
                "angle": 0
            },
            "modern": {
                "fontname": "Montserrat-Bold",
                "fontsize": 40,
                "primarycolor": "&HFFFFFF",
                "secondarycolor": "&H00FF00",
                "outlinecolor": "&H000000",
                "backcolor": "&H80000000",
                "outline": 2,
                "shadow": 0,
                "alignment": 2,
                "marginl": 10,
                "marginr": 10,
                "marginv": 80,
                "borderstyle": 1,
                "scalex": 100,
                "scaley": 100,
                "spacing": 0,
                "angle": 0
            }
        }
    
    def generate_ass_file(self, words_data: List[Dict], style: str = "opus", video_duration: float = 10.0) -> str:
        """Генерация ASS-файла с двумя строками и эффектом увеличения/цвета"""
        style_config = self.styles.get(style, self.styles["opus"])
        ass_filename = f"subtitles_{uuid.uuid4().hex[:8]}.ass"
        ass_path = os.path.join(Config.ASS_DIR, ass_filename)
        
        ass_content = "[Script Info]\n"
        ass_content += "Title: AgentFlow AI Clips Opus Subtitles\n"
        ass_content += "ScriptType: v4.00+\n"
        ass_content += "WrapStyle: 2\n"
        ass_content += "PlayResX: 1080\n"
        ass_content += "PlayResY: 1920\n"
        ass_content += "ScaledBorderAndShadow: yes\n"
        ass_content += "YCbCr Matrix: TV.709\n\n"
        
        ass_content += "[V4+ Styles]\n"
        ass_content += "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, ScaleX, ScaleY, Spacing, Angle, Encoding\n"
        ass_content += (f"Style: Default,{style_config['fontname']},{style_config['fontsize']},"
                       f"{style_config['primarycolor']},{style_config['secondarycolor']},"
                       f"{style_config['outlinecolor']},{style_config['backcolor']},-1,0,"
                       f"{style_config['borderstyle']},{style_config['outline']},{style_config['shadow']},"
                       f"{style_config['alignment']},{style_config['marginl']},{style_config['marginr']},"
                       f"{style_config['marginv']},{style_config['scalex']},{style_config['scaley']},"
                       f"{style_config['spacing']},{style_config['angle']},1\n\n")
        
        ass_content += "[Events]\n"
        ass_content += "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        
        phrases = self._group_words_into_phrases(words_data, max_chars_per_line=440)
        for phrase in phrases:
            start_time = self._seconds_to_ass_time(phrase['start'])
            end_time = self._seconds_to_ass_time(phrase['end'])
            highlighted_text = self._create_highlight_effect(phrase['words'])
            ass_content += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{highlighted_text}\n"
        
        with open(ass_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        logger.info(f"✅ ASS-файл создан: {ass_path}")
        return ass_path
    
    def _group_words_into_phrases(self, words_data: List[Dict], max_chars_per_line: int = 440) -> List[Dict]:
        """Группировка слов в фразы с учетом двух строк и 880 px ширины"""
        phrases = []
        current_phrase = []
        current_chars = 0
        for word_data in words_data:
            word = word_data['word'].strip()
            if not word:
                continue
            word_length = len(word) + 1  # Плюс пробел
            if current_chars + word_length > max_chars_per_line and current_phrase:
                phrases.append({
                    'words': current_phrase.copy(),
                    'start': current_phrase[0]['start'],
                    'end': current_phrase[-1]['end']
                })
                current_phrase = [word_data]
                current_chars = word_length
            else:
                current_phrase.append(word_data)
                current_chars += word_length
            if word.endswith(('.', '!', '?')) and current_phrase:
                phrases.append({
                    'words': current_phrase.copy(),
                    'start': current_phrase[0]['start'],
                    'end': current_phrase[-1]['end']
                })
                current_phrase = []
                current_chars = 0
        if current_phrase:
            phrases.append({
                'words': current_phrase,
                'start': current_phrase[0]['start'],
                'end': current_phrase[-1]['end']
            })
        return phrases[:2]  # Ограничение двумя строками
    
    def _create_highlight_effect(self, words: List[Dict]) -> str:
        """Создание эффекта увеличения и смены цвета слова во время произношения"""
        text_parts = []
        for i, word_data in enumerate(words):
            word = word_data['word'].strip()
            if not word:
                continue
            start_time = max(0, word_data['start'])
            end_time = min(word_data['end'], words[-1]['end'] if i == len(words) - 1 else words[i + 1]['start'])
            duration = max(50, min(500, int((end_time - start_time) * 1000)))
            effect_str = f"{{t({int(start_time*1000)},{int(end_time*1000)},fs{int(45*1.1)},c&H00FF00&)}}"
            text_parts.append(effect_str + word + "{r}")
            if i < len(words) - 1:
                text_parts.append(" ")
        return "".join(text_parts)
    
    def _seconds_to_ass_time(self, seconds: float) -> str:
        """Конвертация секунд в формат времени ASS с высокой точностью"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centiseconds = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

# Инициализация системы субтитров
ass_subtitle_system = ASSKaraokeSubtitleSystem()

def create_clip_with_ass_subtitles(
    video_path: str, 
    start_time: float, 
    end_time: float, 
    words_data: List[Dict],
    output_path: str,
    format_type: str = "9:16",
    style: str = "opus"
) -> bool:
    """Создание клипа с ASS-субтитрами в формате 1080x1920 с детальной обработкой"""
    try:
        logger.info(f"🎬 Начало создания клипа: {start_time}-{end_time}s, стиль: {style}")
        format_type = format_type.replace('_', ':')
        if format_type != "9:16":
            logger.warning(f"⚠️ Формат {format_type} не поддерживается, используется 9:16")
        
        crop_params = {
            "scale": "1080:1920",
            "crop": "1080:1920:0:0"
        }
        
        clip_words = []
        logger.info(f"🔍 Фильтрация слов для клипа {start_time}s-{end_time}s из {len(words_data)} слов")
        for word_data in words_data:
            word_start = word_data['start']
            word_end = word_data['end']
            if word_end > start_time and word_start < end_time:
                clip_word_start = max(0, word_start - start_time)
                clip_word_end = min(end_time - start_time, word_end - start_time)
                if clip_word_end > clip_word_start:
                    clip_words.append({
                        'word': word_data['word'],
                        'start': clip_word_start,
                        'end': clip_word_end
                    })
                    logger.debug(f"✅ Слово '{word_data['word']}' добавлено: {clip_word_start:.1f}s-{clip_word_end:.1f}s")
        
        logger.info(f"📝 Найдено {len(clip_words)} слов для субтитров")
        temp_video_path = output_path.replace('.mp4', '_temp.mp4')
        
        nvenc_available = 'h264_nvenc' in ffmpeg_available_codecs()
        codec = 'h264_nvenc' if nvenc_available else 'libx264'
        
        base_cmd = [
            'ffmpeg', '-i', video_path,
            '-ss', str(start_time),
            '-t', str(end_time - start_time),
            '-vf', f"scale={crop_params['scale']},crop={crop_params['crop']}",
            '-c:v', codec, '-preset', 'ultrafast',
            '-c:a', 'aac', '-b:a', '64k',
            '-y', temp_video_path
        ]
        
        logger.info("🎬 ЭТАП 1: Создание базового видео с обрезкой")
        result = subprocess.run(base_cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=120)
        if result.returncode != 0:
            logger.error(f"❌ ЭТАП 1 завершен с ошибкой: {result.stderr}")
            return False
        
        logger.info("✅ ЭТАП 1 завершен: базовое видео создано")
        
        if clip_words:
            try:
                logger.info("📝 ЭТАП 2: Создание и наложение ASS-субтитров")
                ass_path = ass_subtitle_system.generate_ass_file(clip_words, style, end_time - start_time)
                if ass_path:
                    subtitle_cmd = [
                        'ffmpeg', '-i', temp_video_path,
                        '-vf', f"ass={ass_path}",
                        '-c:v', codec, '-preset', 'ultrafast',
                        '-c:a', 'copy',
                        '-y', output_path
                    ]
                    logger.info("📝 Применение ASS-субтитров к видео")
                    result = subprocess.run(subtitle_cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=120)
                    if result.returncode != 0:
                        logger.error(f"❌ ЭТАП 2 завершен с ошибкой: {result.stderr}")
                        if os.path.exists(temp_video_path):
                            os.rename(temp_video_path, output_path)
                        return True
                    logger.info("✅ ЭТАП 2 завершен: субтитры наложены")
                    os.remove(ass_path)
                else:
                    logger.warning("⚠️ ASS-файл не создан, пропуск наложения")
            except Exception as e:
                logger.error(f"❌ Ошибка в ЭТАПЕ 2: {str(e)}")
                if os.path.exists(temp_video_path):
                    os.rename(temp_video_path, output_path)
                return True
        else:
            if os.path.exists(temp_video_path):
                os.rename(temp_video_path, output_path)
            logger.info("✅ Клип создан без субтитров (нет слов)")
        
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        logger.info(f"✅ Временные файлы удалены, клип готов: {output_path}")
        return True
    except subprocess.TimeoutExpired as te:
        logger.error(f"❌ Таймаут при создании клипа: {str(te)}")
        if os.path.exists(temp_video_path):
            os.rename(temp_video_path, output_path)
        return False
    except Exception as e:
        logger.error(f"❌ Общая ошибка создания клипа: {str(e)}")
        if os.path.exists(temp_video_path):
            os.rename(temp_video_path, output_path)
        return False

def get_crop_parameters(width: int, height: int, format_type: str) -> Optional[Dict]:
    """Получение параметров обрезки для заданного формата видео с детальной логикой"""
    formats = {
        "9:16": {"target_width": 1080, "target_height": 1920},
        "16:9": {"target_width": 1920, "target_height": 1080},
        "1:1": {"target_width": 1080, "target_height": 1080},
        "4:5": {"target_width": 1080, "target_height": 1350}
    }
    if format_type not in formats:
        logger.error(f"❌ Неподдерживаемый формат видео: {format_type}")
        return None
    target = formats[format_type]
    scale_x = target["target_width"] / width
    scale_y = target["target_height"] / height
    scale = max(scale_x, scale_y)
    new_width = int(width * scale)
    new_height = int(height * scale)
    crop_x = (new_width - target["target_width"]) // 2
    crop_y = (new_height - target["target_height"]) // 2
    return {
        "scale": f"{new_width}:{new_height}",
        "crop": f"{target['target_width']}:{target['target_height']}:{crop_x}:{crop_y}"
    }

def check_memory_available() -> bool:
    """Проверка доступной памяти с детальным мониторингом"""
    memory = psutil.virtual_memory()
    available_mb = memory.available / (1024 * 1024)
    logger.debug(f"Доступно памяти: {available_mb:.1f} MB из {memory.total / (1024 * 1024):.1f} MB")
    return memory.available > 50 * 1024 * 1024

# Эндпоинты API
@app.get("/")
async def root():
    """Основной эндпоинт для проверки статуса сервиса"""
    return {"message": "AgentFlow AI Clips API v18.3.0", "status": "running", "timestamp": datetime.now().isoformat()}

@app.get("/health")
async def health_check():
    """Проверка состояния системы с детальной информацией"""
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    cpu = psutil.cpu_percent(interval=1)
    return {
        "status": "healthy",
        "version": "18.3.0",
        "timestamp": datetime.now().isoformat(),
        "system": {
            "memory_usage": f"{memory.percent}% ({memory.available / (1024 * 1024):.1f} MB доступно из {memory.total / (1024 * 1024):.1f} MB)",
            "disk_usage": f"{disk.percent}% ({disk.free / (1024 * 1024):.1f} MB свободно)",
            "cpu_usage": f"{cpu}%",
            "tasks_running": len(analysis_tasks) + len(generation_tasks)
        },
        "services": {
            "openai": "connected" if openai_api_key else "disconnected",
            "supabase": "connected" if supabase_available else "disconnected"
        }
    }

@app.post("/api/videos/upload")
async def upload_video(file: UploadFile = File(...)):
    """Загрузка видео файла с проверкой памяти и валидацией"""
    if not check_memory_available():
        raise HTTPException(status_code=503, detail="Недостаточно доступной памяти для обработки")
    if file.size and file.size > Config.MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Файл превышает лимит 200 MB")
    video_id = str(uuid.uuid4())
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
        raise HTTPException(status_code=400, detail="Неподдерживаемый формат")
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
    logger.info(f"✅ Видео загружено: {video_id}, длительность: {duration:.1f}s")
    return {
        "video_id": video_id,
        "filename": file.filename,
        "duration": duration,
        "size": len(content),
        "upload_time": analysis_tasks[video_id]["upload_time"],
        "status": "uploaded"
    }

@app.post("/api/videos/analyze")
async def analyze_video(request: VideoAnalysisRequest, background_tasks: BackgroundTasks):
    """Запуск анализа видео в фоновом режиме с проверкой статуса"""
    video_id = request.video_id
    if video_id not in analysis_tasks or not check_memory_available():
        raise HTTPException(status_code=404, detail="Видео не найдено или память исчерпана")
    background_tasks.add_task(analyze_video_task, video_id)
    analysis_tasks[video_id]["status"] = "analyzing"
    logger.info(f"🔍 Запущен анализ видео: {video_id}")
    return {"message": "Анализ запущен", "video_id": video_id}

async def analyze_video_task(video_id: str):
    """Фоновая задача анализа видео с обработкой ошибок и мониторингом"""
    try:
        analysis_task = analysis_tasks[video_id]
        video_path = analysis_task["video_path"]
        video_duration = analysis_task["duration"]
        logger.info(f"🔍 Начало анализа видео: {video_id}, длительность: {video_duration}s")
        audio_path = os.path.join(Config.AUDIO_DIR, f"{video_id}.mp3")
        if not extract_audio(video_path, audio_path):
            raise Exception("Ошибка извлечения аудио")
        logger.info(f"🎵 Аудио извлечено: {audio_path}")
        transcript_data = safe_transcribe_audio(audio_path)
        if not transcript_data:
            raise Exception("Ошибка транскрибации")
        logger.info("📝 Транскрибация успешно завершена")
        transcript_text = transcript_data.get('text', '')
        analysis_result = analyze_with_chatgpt(transcript_text, video_duration)
        if not analysis_result:
            analysis_result = create_fallback_highlights(video_duration, 3)
        analysis_tasks[video_id].update({
            "status": "completed",
            "transcript": transcript_data,
            "analysis": analysis_result,
            "completed_at": datetime.now().isoformat()
        })
        logger.info(f"✅ Анализ завершен: {video_id}, найдено {len(analysis_result['highlights'])} клипов")
    except Exception as e:
        logger.error(f"❌ Ошибка анализа видео {video_id}: {str(e)}")
        analysis_tasks[video_id].update({
            "status": "error",
            "error": str(e),
            "completed_at": datetime.now().isoformat()
        })

@app.get("/api/videos/{video_id}/status")
async def get_video_status(video_id: str):
    """Получение статуса анализа видео с дополнительной информацией"""
    if video_id not in analysis_tasks:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    task = analysis_tasks[video_id]
    response = {
        "video_id": video_id,
        "status": task["status"],
        "filename": task.get("filename"),
        "duration": task.get("duration"),
        "upload_time": task.get("upload_time"),
        "memory_check": check_memory_available()
    }
    if task["status"] == "completed":
        response["highlights"] = task.get("analysis", {}).get("highlights", [])
    if task["status"] == "error":
        response["error"] = task.get("error")
    return response

@app.post("/api/clips/generate")
async def generate_clips(request: ClipGenerationRequest, background_tasks: BackgroundTasks):
    """Запуск генерации клипов с проверкой очереди и ресурсов"""
    if not check_memory_available():
        raise HTTPException(status_code=503, detail="Недостаточно памяти для генерации")
    video_id = request.video_id
    format_id = request.format_id
    style_id = request.style_id
    if video_id not in analysis_tasks or analysis_tasks[video_id]["status"] != "completed":
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
    task_queue.append(task_id)
    if len(task_queue) > 1:
        logger.info(f"⚠️ Задача {task_id} добавлена в очередь, текущая длина: {len(task_queue)}")
        return {"task_id": task_id, "message": "Задача в очереди"}
    background_tasks.add_task(generate_clips_task, task_id)
    logger.info(f"🚀 Запущена генерация клипов: {task_id}")
    return {
        "task_id": task_id,
        "message": "Генерация клипов запущена",
        "video_id": video_id,
        "format_id": format_id,
        "style_id": style_id
    }

async def generate_clips_task(task_id: str):
    """Фоновая задача генерации клипов с управлением очередью и детальной логикой"""
    if task_queue[0] != task_id:
        logger.info(f"⚠️ Ожидание в очереди для задачи {task_id}")
        while task_queue[0] != task_id:
            await asyncio.sleep(5)
    task = generation_tasks[task_id]
    video_id = task["video_id"]
    format_id = task["format_id"]
    style_id = task["style_id"]
    analysis_task = analysis_tasks[video_id]
    video_path = analysis_task["video_path"]
    highlights = analysis_task["analysis"]["highlights"]
    transcript_data = analysis_task.get("transcript", {})
    
    generation_tasks[task_id]["status"] = "generating"
    logger.info(f"🎬 Начало генерации {len(highlights)} клипов для задачи {task_id}")
    
    clips_created = 0
    total_clips = len(highlights)
    for i, highlight in enumerate(highlights):
        if not check_memory_available():
            logger.warning("⚠️ Недостаточно памяти, прерывание генерации")
            break
        logger.info(f"🎬 Создание клипа {i+1}/{total_clips}: {highlight['start_time']}-{highlight['end_time']}s")
        progress = int((i / total_clips) * 100)
        generation_tasks[task_id]["progress"] = progress
        generation_tasks[task_id]["current_stage"] = f"Создание клипа {i+1}/{total_clips}"
        
        audio_path = os.path.join(Config.AUDIO_DIR, f"{task_id}_clip_{i}.mp3")
        if not extract_audio(video_path, audio_path, highlight["start_time"], highlight["end_time"] - highlight["start_time"]):
            logger.error(f"❌ Ошибка извлечения аудио для клипа {i+1}")
            continue
        clip_transcript = safe_transcribe_audio(audio_path)
        words_in_range = clip_transcript.get('words', []) if clip_transcript else []
        
        logger.info(f"📝 Найдено {len(words_in_range)} слов для субтитров")
        clip_filename = f"{task_id}_clip_{i+1}_{format_id.replace(':', 'x')}.mp4"
        clip_path = os.path.join(Config.CLIPS_DIR, clip_filename)
        
        success = create_clip_with_ass_subtitles(
            video_path, highlight["start_time"], highlight["end_time"], words_in_range, clip_path, format_id, style_id
        )
        if success:
            supabase_url = upload_clip_to_supabase(clip_path, clip_filename)
            clip_info = {
                "id": f"{task_id}_clip_{i+1}",
                "title": highlight.get("title", f"Клип {i+1}"),
                "description": highlight.get("description", ""),
                "start_time": highlight["start_time"],
                "end_time": highlight["end_time"],
                "duration": highlight["end_time"] - highlight["start_time"],
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
    
    generation_tasks[task_id].update({
        "status": "completed",
        "progress": 100,
        "current_stage": "Завершено",
        "clips_created": clips_created,
        "completed_at": datetime.now().isoformat()
    })
    task_queue.popleft()
    logger.info(f"🎉 Генерация завершена: {task_id}, создано {clips_created} клипов")

@app.get("/api/clips/generation/{task_id}/status")
async def get_generation_status(task_id: str):
    """Получение статуса генерации клипов с дополнительной информацией"""
    if task_id not in generation_tasks:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    task = generation_tasks[task_id]
    response = {
        "task_id": task_id,
        "status": task["status"],
        "progress": task.get("progress", 0),
        "current_stage": task.get("current_stage"),
        "clips_created": len(task.get("clips", [])),
        "created_at": task.get("created_at"),
        "memory_check": check_memory_available()
    }
    if task["status"] == "completed":
        response["clips"] = task.get("clips", [])
        response["completed_at"] = task.get("completed_at")
    return response

@app.get("/api/clips/download/{filename}")
async def download_clip(filename: str):
    """Скачивание сгенерированного клипа с проверкой доступа"""
    file_path = os.path.join(Config.CLIPS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=filename
    )

# Дополнительная утилита для очистки старых файлов
async def cleanup_old_files():
    """Удаление старых файлов из директорий"""
    current_time = datetime.now()
    for directory in [Config.UPLOAD_DIR, Config.AUDIO_DIR, Config.CLIPS_DIR, Config.ASS_DIR]:
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if os.path.isfile(file_path):
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                if (current_time - file_time).total_seconds() > Config.MAX_TASK_AGE:
                    os.remove(file_path)
                    logger.info(f"🗑 Удален старый файл: {file_path}")

# Планировщик очистки
async def cleanup_scheduler():
    """Планировщик периодической очистки файлов"""
    while True:
        await asyncio.sleep(Config.CLEANUP_INTERVAL)
        await cleanup_old_files()
        logger.info("🕒 Выполнена периодическая очистка старых файлов")

# Запуск планировщика при старте приложения
@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске приложения"""
    logger.info("🚀 AgentFlow AI Clips v18.3.0 успешно запущен!")
    logger.info("🎬 Система ASS субтитров активирована с поддержкой Montserrat-Bold")
    logger.info("🔥 GPU-ускорение через libass (если доступно)")
    logger.info("⚡ Двухэтапная генерация клипов с оптимизацией")
    logger.info("🕒 Запущен планировщик очистки файлов")
    asyncio.create_task(cleanup_scheduler())

# Запуск приложения с подробной информацией
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
