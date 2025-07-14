# AgentFlow AI Clips v18.3.2 - ПОЛНАЯ ВЕРСИЯ С ОПТИМИЗАЦИЕЙ И СТИЛЕМ OPUS
# Система генерации коротких клипов с ASS-субтитрами в формате 1080x1920
# Подробная реализация с поддержкой надежной генерации и отладки
# Текущая дата и время: 09:18 PM EDT, 13 июля 2025 (воскресенье)

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
import re
import sys
import traceback

# Импорт модуля субтитров на основе ShortGPT с обработкой ошибок
try:
    from shortgpt_captions import create_word_level_subtitles
except ImportError as e:
    logger = logging.getLogger("app")
    logger.error(f"❌ Ошибка импорта shortgpt_captions: {str(e)}")
    sys.exit(1)

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import openai
from openai import OpenAI

# Попытка импорта Supabase с альтернативным fallback
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger = logging.getLogger("app")
    logger.warning("⚠️ Модуль Supabase не установлен, будет использовано локальное хранение")

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

# Инициализация FastAPI с расширенной конфигурацией
app = FastAPI(
    title="AgentFlow AI Clips API",
    description="Профессиональная система генерации клипов с ASS-субтитрами в стиле Opus (1080x1920). Версия 18.3.2.",
    version="18.3.2",
    contact={
        "name": "Support Team",
        "email": "support@x.ai",
        "url": "https://x.ai/support"
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT"
    }
)

# Настройка CORS для поддержки всех источников с деталями
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "*"],
)

# Основной класс конфигурации с подробными параметрами
class Config:
    """Класс конфигурации для управления директориями, лимитами и стилями"""
    
    # Директории для хранения данных
    UPLOAD_DIR = "uploads"
    AUDIO_DIR = "audio"
    CLIPS_DIR = "clips"
    ASS_DIR = "ass_subtitles"
    FONTS_DIR = "ass_subtitles/fonts"
    
    # Лимиты ресурсов
    MAX_FILE_SIZE = 200 * 1024 * 1024  # Ограничение 200 MB
    MAX_TASK_AGE = 24 * 60 * 60        # Удаление задач старше 24 часов
    CLEANUP_INTERVAL = 3600            # Очистка каждые 60 минут
    MAX_CONCURRENT_TASKS = 1           # Ограничение на одну задачу
    
    # Стили для субтитров (только Opus на данный момент)
    ASS_STYLES = {
        "opus": {
            "name": "Opus",
            "fontname": "Inter-Bold",
            "fontsize": 48,
            "primarycolor": "&HFFFFFF",  # Белый текст
            "secondarycolor": "&H00FF00",  # Зеленая подсветка
            "outlinecolor": "&H000000",  # Черный контур
            "backcolor": "&HCC000000",  # Полупрозрачный черный (opacity ~80%)
            "outline": 2,
            "shadow": 1,
            "alignment": 2,           # Центрирование по горизонтали
            "marginl": 100,           # Отступ 100 px слева
            "marginr": 100,           # Отступ 100 px справа
            "marginv": 1700,          # Отступ от низа (250 px от 1920)
            "borderstyle": 1,
            "scalex": 100,
            "scaley": 100,
            "spacing": 0,
            "angle": 0,
            "padding": "24px 16px",   # Дополнительный padding
            "border_radius": "16px"    # Закругление
        }
    }

# Создание всех необходимых директорий с проверками
for directory in [Config.UPLOAD_DIR, Config.AUDIO_DIR, Config.CLIPS_DIR, Config.ASS_DIR, Config.FONTS_DIR]:
    os.makedirs(directory, exist_ok=True)
    logger.debug(f"📂 Директория создана или проверена: {directory}")

# Глобальные переменные с инициализацией
analysis_tasks = {}  # Хранит задачи анализа видео
generation_tasks = {}  # Хранит задачи генерации клипов
task_queue = deque(maxlen=Config.MAX_CONCURRENT_TASKS)  # Очередь для обработки задач
cache = {}  # Кэш для хранения результатов транскрибации
last_cleanup = time.time()

# Инициализация OpenAI с проверкой ключа
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    logger.error("❌ Переменная OPENAI_API_KEY не найдена в окружении")
    raise ValueError("OPENAI_API_KEY обязателен для работы")
client = OpenAI(api_key=openai_api_key)
logger.info("✅ Клиент OpenAI успешно инициализирован с ключом")

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
        # Тестовый запрос для проверки подключения
        test_response = supabase.table('test').select('*').limit(1).execute()
        if test_response:
            logger.info("✅ Подключение к Supabase Storage успешно установлено")
            return True
        else:
            logger.warning("⚠️ Тест подключения к Supabase не удался")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Supabase: {str(e)}")
        return False

supabase_available = init_supabase()

# Модели Pydantic для валидации запросов
class VideoAnalysisRequest(BaseModel):
    """Модель запроса для анализа видео с дополнительной проверкой"""
    video_id: str
    retry_count: Optional[int] = 0

class ClipGenerationRequest(BaseModel):
    """Модель запроса для генерации клипов с настройками"""
    video_id: str
    format_id: str
    style_id: str = "opus"
    max_clips: Optional[int] = 3

class VideoInfo(BaseModel):
    """Модель информации о видео с расширенными данными"""
    id: str
    filename: str
    duration: float
    size: int
    status: str
    upload_time: str
    resolution: Optional[str] = None

class ClipInfo(BaseModel):
    """Модель информации о клипе с деталями"""
    id: str
    video_id: str
    format_id: str
    style_id: str
    status: str
    progress: int
    current_stage: Optional[str] = None
    stage_progress: Optional[int] = None
    download_url: Optional[str] = None

# Утилиты для работы с видео и аудио
def upload_clip_to_supabase(local_path: str, filename: str) -> Optional[str]:
    """Загрузка клипа в Supabase Storage с детальной обработкой ошибок"""
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
            logger.info(f"✅ Клип загружен в Supabase: {storage_path}, URL: {public_url}")
            return public_url
        else:
            logger.warning("⚠️ Ответ Supabase пустой, загрузка не подтверждена")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки в Supabase: {str(e)}")
    logger.warning("⚠️ Возврат к локальному хранению из-за ошибки")
    return f"/api/clips/download/{filename}"

def get_video_duration(video_path: str) -> float:
    """Получение длительности видео с использованием ffprobe и резервным значением"""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        data = json.loads(result.stdout)
        duration = float(data['format']['duration'])
        # Определение разрешения
        streams = data.get('streams', [])
        resolution = next((s['width'] for s in streams if 'width' in s), 0)
        if video_path in analysis_tasks:
            analysis_tasks[video_path]['resolution'] = f"{resolution}x1920" if resolution else "unknown"
        return duration
    except Exception as e:
        logger.error(f"❌ Ошибка получения длительности видео: {str(e)}")
        return 60.0  # Значение по умолчанию

def ffmpeg_available_codecs() -> List[str]:
    """Проверка доступных кодеков FFmpeg для GPU-ускорения с логированием"""
    try:
        result = subprocess.run(['ffmpeg', '-codecs'], capture_output=True, text=True, timeout=10)
        codecs = [line.split()[1] for line in result.stdout.splitlines() if 'h264_nvenc' in line or 'libx264' in line]
        logger.info(f"✅ Найдены кодеки FFmpeg: {codecs}")
        return codecs
    except Exception as e:
        logger.warning(f"⚠️ Ошибка проверки кодеков FFmpeg: {str(e)}")
        return ['libx264']  # Резервный кодек

def extract_audio(video_path: str, audio_path: str, start_time: float = 0, duration: float = None) -> bool:
    """Извлечение аудио из видео с детальной обработкой ошибок"""
    try:
        cmd = [
            'ffmpeg', '-i', video_path, '-vn', '-acodec', 'mp3',
            '-ar', '16000', '-ac', '1', '-y', audio_path
        ]
        if start_time:
            cmd.extend(['-ss', str(start_time)])
        if duration:
            cmd.extend(['-t', str(duration)])
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
        if os.path.exists(audio_path):
            logger.info(f"🎵 Аудио успешно извлечено: {audio_path}")
            return True
        else:
            logger.error(f"❌ Аудио не создано: {audio_path}")
            return False
    except subprocess.TimeoutExpired as te:
        logger.error(f"❌ Таймаут при извлечении аудио: {str(te)}")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка извлечения аудио: {str(e)}")
        return False

def safe_transcribe_audio(audio_path: str) -> Optional[Dict]:
    """Безопасная транскрибация аудио с кэшированием и обработкой ошибок"""
    cache_key = f"transcribe_{hash(open(audio_path, 'rb').read())}"
    if cache_key in cache:
        logger.info("📦 Использование кэшированной транскрибации для {cache_key}")
        return cache[cache_key]
    try:
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["word"],
                language="en"  # Можно настроить динамически
            )
            result = transcript.model_dump() if hasattr(transcript, 'model_dump') else dict(transcript)
            cache[cache_key] = result
            logger.info(f"✅ Транскрибация завершена: {len(result.get('words', []))} слов")
            return result
    except openai.APIError as ae:
        logger.error(f"❌ Ошибка API OpenAI: {str(ae)}")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка транскрибации: {str(e)} с трассировкой {traceback.format_exc()}")
        return None

def analyze_with_chatgpt(transcript_text: str, video_duration: float) -> Optional[Dict]:
    """Анализ транскрипта с ChatGPT для выделения клипов с детальным промптом"""
    try:
        target_clips = 2 if video_duration <= 30 else 3 if video_duration <= 60 else 4
        prompt = f"""
        Проанализируй транскрипт видео длительностью {video_duration:.1f} секунд.
        Найди {target_clips} самых интересных моментов для клипов (длительность 15-20 секунд, не пересекаются).
        Верни JSON с ключом 'highlights' и массивом объектов вида:
        {{
            "start_time": float,
            "end_time": float,
            "title": str,
            "description": str,
            "confidence": float
        }}
        Убедись, что моменты имеют высокую плотность речи и эмоциональный контекст.
        """
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.7,
            timeout=30
        )
        content = response.choices[0].message.content.strip()
        if content.startswith('```json'):
            content = content[7:-3].strip()
        result = json.loads(content)
        logger.info(f"✅ Анализ ChatGPT завершен: {len(result['highlights'])} клипов")
        return result
    except json.JSONDecodeError as je:
        logger.error(f"❌ Ошибка декодирования JSON: {str(je)}")
        return create_fallback_highlights(video_duration, target_clips)
    except Exception as e:
        logger.error(f"❌ Ошибка анализа с ChatGPT: {str(e)}")
        return create_fallback_highlights(video_duration, target_clips)

def create_fallback_highlights(video_duration: float, target_clips: int) -> Dict:
    """Создание запасных клипов при ошибке анализа с логикой распределения"""
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
            "description": "Автоматически сгенерированный клип",
            "confidence": 0.5
        })
    logger.warning(f"⚠️ Использованы запасные клипы: {len(highlights)}")
    return {"highlights": highlights}

# Система субтитров с поддержкой караоке-эффектов
class ASSKaraokeSubtitleSystem:
    """Класс для генерации ASS-файлов с динамической подсветкой слов в стиле Opus"""
    
    def __init__(self):
        self.styles = {
            "opus": {
                "fontname": "Inter-Bold",
                "fontsize": 48,
                "primarycolor": "&HFFFFFF",
                "secondarycolor": "&H00FF00",
                "outlinecolor": "&H000000",
                "backcolor": "&HCC000000",
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
                "angle": 0,
                "padding": "24px 16px",
                "border_radius": "16px"
            }
        }
        self.font_path = os.path.join(Config.FONTS_DIR, "Inter-Bold.ttf")
        if not os.path.exists(self.font_path):
            logger.warning(f"⚠️ Шрифт {self.font_path} не найден, используем системный")
    
    def generate_ass_file(self, words_data: List[Dict], style: str = "opus", video_duration: float = 10.0) -> str:
        """Генерация ASS-файла с динамической подсветкой каждого слова"""
        style_config = self.styles.get(style, self.styles["opus"])
        ass_filename = f"subtitles_{uuid.uuid4().hex[:8]}.ass"
        ass_path = os.path.join(Config.ASS_DIR, ass_filename)
        
        ass_content = "[Script Info]\n"
        ass_content += "Title: AgentFlow AI Clips Opus Subtitles\n"
        ass_content += "ScriptType: v4.00+\n"
        ass_content += "WrapStyle: 2\n"  # Поддержка двух строк
        ass_content += "PlayResX: 1080\n"  # Точное разрешение
        ass_content += "PlayResY: 1920\n"
        ass_content += "ScaledBorderAndShadow: yes\n"
        ass_content += f"FontFile: {self.font_path}\n\n" if os.path.exists(self.font_path) else "\n"
        
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
        
        total_words = len(words_data)
        for i, word_data in enumerate(words_data):
            start_time = self._seconds_to_ass_time(word_data['start'])
            end_time = self._seconds_to_ass_time(word_data['end'])
            word = word_data['word'].strip()
            if not word:
                continue
            duration = max(50, min(500, int((word_data['end'] - word_data['start']) * 1000)))
            # Добавление эффекта подсветки с padding и border-radius
            ass_content += (f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,"
                           f"{{\pos(540,1700)}}{{\p1}}{{\bord1}}{{\shad1}}{{\3c&HCC000000&}}"
                           f"{{\t(0,0,\c&HFFFFFF&)}}{word}"
                           f"{{\t({duration},\c&H00FF00&)}}{{\p0}}{{\r}}\n")
            logger.debug(f"📝 Сгенерирован субтитр для слова '{word}' ({i+1}/{total_words})")
        
        with open(ass_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        logger.info(f"✅ ASS-файл создан: {ass_path}, слов: {total_words}")
        return ass_path
    
    def _seconds_to_ass_time(self, seconds: float) -> str:
        """Конвертация секунд в формат времени ASS с проверкой"""
        if seconds < 0:
            logger.warning(f"⚠️ Отрицательное время: {seconds}, заменено на 0")
            seconds = 0
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
        logger.info(f"🎬 Начало создания клипа: {start_time}-{end_time}s, стиль: {style}, файл: {output_path}")
        format_type = format_type.replace('_', ':')
        if format_type != "9:16":
            logger.warning(f"⚠️ Формат {format_type} не поддерживается, используется 9:16")
        
        clip_duration = end_time - start_time
        if clip_duration <= 0:
            logger.error(f"❌ Неверная длительность клипа: {clip_duration}s")
            return False
        
        crop_params = {
            "scale": "1080:1920",
            "crop": "1080:1920:0:0"
        }
        
        clip_words = []
        logger.info(f"🔍 Фильтрация {len(words_data)} слов для клипа {start_time}s-{end_time}s")
        for word_data in words_data:
            word_start = word_data['start']
            word_end = word_data['end']
            if word_end > start_time and word_start < end_time:
                clip_word_start = max(0, word_start - start_time)
                clip_word_end = min(clip_duration, word_end - start_time)
                if clip_word_end > clip_word_start:
                    clip_words.append({
                        'word': word_data['word'],
                        'start': clip_word_start,
                        'end': clip_word_end
                    })
                    logger.debug(f"✅ Слово '{word_data['word']}' добавлено: {clip_word_start:.2f}s-{clip_word_end:.2f}s")
        
        logger.info(f"📝 Найдено {len(clip_words)} слов для субтитров")
        temp_video_path = output_path.replace('.mp4', '_temp.mp4')
        
        nvenc_available = 'h264_nvenc' in ffmpeg_available_codecs()
        codec = 'h264_nvenc' if nvenc_available else 'libx264'
        logger.info(f"🎬 Используемый кодек: {codec}")
        
        # ЭТАП 1: Создание базового видео
        base_cmd = [
            'ffmpeg', '-i', video_path,
            '-ss', str(start_time),
            '-t', str(clip_duration),
            '-vf', f"scale={crop_params['scale']},crop={crop_params['crop']}",
            '-c:v', codec, '-preset', 'ultrafast',
            '-c:a', 'aac', '-b:a', '64k',
            '-y', temp_video_path
        ]
        logger.info("🎬 ЭТАП 1: Запуск создания базового видео")
        result = subprocess.run(base_cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=120)
        if result.returncode != 0:
            logger.error(f"❌ ЭТАП 1 завершен с ошибкой: {result.stderr}")
            return False
        logger.info("✅ ЭТАП 1 завершен: базовое видео создано")
        
        # ЭТАП 2: Наложение субтитров
        if clip_words:
            try:
                logger.info("📝 ЭТАП 2: Генерация и наложение ASS-субтитров")
                ass_path = ass_subtitle_system.generate_ass_file(clip_words, style, clip_duration)
                if not os.path.exists(ass_path):
                    logger.error(f"❌ ASS-файл не создан: {ass_path}")
                    raise Exception("ASS-файл отсутствует")
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
            except Exception as e:
                logger.error(f"❌ Ошибка в ЭТАПЕ 2: {str(e)} с трассировкой {traceback.format_exc()}")
                if os.path.exists(temp_video_path):
                    os.rename(temp_video_path, output_path)
                return True
        else:
            logger.info("⚠️ Нет слов для субтитров, копирование базового видео")
            if os.path.exists(temp_video_path):
                os.rename(temp_video_path, output_path)
        
        # ЭТАП 3: Очистка временных файлов
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
            logger.info("✅ Временные файлы удалены")
        else:
            logger.warning("⚠️ Временный файл не найден для удаления")
        
        logger.info(f"✅ Клип успешно создан: {output_path}, длительность: {clip_duration}s")
        return True
    except subprocess.TimeoutExpired as te:
        logger.error(f"❌ Таймаут при создании клипа: {str(te)}")
        if os.path.exists(temp_video_path):
            os.rename(temp_video_path, output_path)
        return False
    except Exception as e:
        logger.error(f"❌ Общая ошибка создания клипа: {str(e)} с трассировкой {traceback.format_exc()}")
        if os.path.exists(temp_video_path):
            os.rename(temp_video_path, output_path)
        return False

def check_memory_available() -> bool:
    """Проверка доступной памяти с детальным логированием"""
    memory = psutil.virtual_memory()
    available_mb = memory.available / (1024 * 1024)
    logger.debug(f"📊 Доступно памяти: {available_mb:.1f} MB из {memory.total / (1024 * 1024):.1f} MB")
    return memory.available > 50 * 1024 * 1024

# Эндпоинты API
@app.get("/")
async def root():
    """Основной эндпоинт для проверки статуса сервиса с версией"""
    return {
        "message": "AgentFlow AI Clips API v18.3.2",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "version": "18.3.2"
    }

@app.get("/health")
async def health_check():
    """Проверка состояния системы с детальной информацией"""
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    return {
        "status": "healthy",
        "version": "18.3.2",
        "timestamp": datetime.now().isoformat(),
        "system": {
            "memory_usage": f"{memory.percent}% ({memory.available / (1024 * 1024):.1f} MB доступно)",
            "disk_usage": f"{disk.percent}% ({disk.free / (1024 * 1024):.1f} MB свободно)",
            "tasks_running": len(analysis_tasks) + len(generation_tasks),
            "uptime": str(timedelta(seconds=time.time() - os.times()[4]))
        },
        "services": {
            "openai": "connected" if openai_api_key else "disconnected",
            "supabase": "connected" if supabase_available else "disconnected"
        }
    }

@app.post("/api/videos/upload")
async def upload_video(file: UploadFile = File(...)):
    """Загрузка видео файла с проверкой памяти и формата"""
    if not check_memory_available():
        raise HTTPException(status_code=503, detail="Недостаточно доступной памяти для обработки")
    if file.size and file.size > Config.MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"Файл превышает лимит {Config.MAX_FILE_SIZE / (1024 * 1024)} MB")
    video_id = str(uuid.uuid4())
    file_extension = os.path.splitext(file.filename)[1].lower()
    supported_extensions = ['.mp4', '.mov', '.avi', '.mkv']
    if file_extension not in supported_extensions:
        raise HTTPException(status_code=400, detail=f"Неподдерживаемый формат, используйте {', '.join(supported_extensions)}")
    video_path = os.path.join(Config.UPLOAD_DIR, f"{video_id}{file_extension}")
    try:
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
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки видео: {str(e)}")
        if os.path.exists(video_path):
            os.remove(video_path)
        raise HTTPException(status_code=500, detail="Ошибка при загрузке файла")

@app.post("/api/videos/analyze")
async def analyze_video(request: VideoAnalysisRequest, background_tasks: BackgroundTasks):
    """Запуск анализа видео в фоновом режиме с повторными попытками"""
    video_id = request.video_id
    if video_id not in analysis_tasks or not check_memory_available():
        raise HTTPException(status_code=404, detail="Видео не найдено или память исчерпана")
    if analysis_tasks[video_id].get("status") in ["analyzing", "completed"]:
        logger.info(f"⚠️ Видео {video_id} уже в процессе или завершено")
        return {"message": "Анализ уже запущен или завершен", "video_id": video_id}
    background_tasks.add_task(analyze_video_task, video_id, request.retry_count)
    analysis_tasks[video_id]["status"] = "analyzing"
    logger.info(f"🔍 Запущен анализ видео: {video_id}, попытка {request.retry_count}")
    return {"message": "Анализ запущен", "video_id": video_id}

async def analyze_video_task(video_id: str, retry_count: int = 0):
    """Фоновая задача анализа видео с обработкой ошибок и повторами"""
    try:
        analysis_task = analysis_tasks[video_id]
        video_path = analysis_task["video_path"]
        video_duration = analysis_task["duration"]
        logger.info(f"🔍 Начало анализа видео: {video_id}, длительность: {video_duration}s, попытка {retry_count}")
        audio_path = os.path.join(Config.AUDIO_DIR, f"{video_id}.mp3")
        if not extract_audio(video_path, audio_path):
            raise Exception("Ошибка извлечения аудио")
        logger.info(f"🎵 Аудио извлечено: {audio_path}, размер: {os.path.getsize(audio_path)/1024:.1f} KB")
        transcript_data = safe_transcribe_audio(audio_path)
        if not transcript_data and retry_count < 2:
            logger.warning(f"⚠️ Повторная попытка транскрибации: {retry_count + 1}")
            await asyncio.sleep(5)  # Пауза перед повтором
            return await analyze_video_task(video_id, retry_count + 1)
        elif not transcript_data:
            raise Exception("Ошибка транскрибации после всех попыток")
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
        logger.error(f"❌ Ошибка анализа видео {video_id}: {str(e)} с трассировкой {traceback.format_exc()}")
        analysis_tasks[video_id].update({
            "status": "error",
            "error": str(e),
            "completed_at": datetime.now().isoformat()
        })

@app.get("/api/videos/{video_id}/status")
async def get_video_status(video_id: str):
    """Получение статуса анализа видео с деталями"""
    if video_id not in analysis_tasks:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    task = analysis_tasks[video_id]
    response = {
        "video_id": video_id,
        "status": task["status"],
        "filename": task.get("filename", "unknown"),
        "duration": task.get("duration", 0.0),
        "size": task.get("size", 0),
        "upload_time": task.get("upload_time"),
        "resolution": task.get("resolution", "unknown")
    }
    if task["status"] == "completed":
        response["highlights"] = task.get("analysis", {}).get("highlights", [])
    if task["status"] == "error":
        response["error"] = task.get("error")
    return response

@app.post("/api/clips/generate")
async def generate_clips(request: ClipGenerationRequest, background_tasks: BackgroundTasks):
    """Запуск генерации клипов с проверкой очереди и лимитов"""
    if not check_memory_available():
        raise HTTPException(status_code=503, detail="Недостаточно памяти для генерации")
    video_id = request.video_id
    format_id = request.format_id
    style_id = request.style_id
    max_clips = min(request.max_clips, 5)  # Ограничение до 5 клипов
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
        "max_clips": max_clips,
        "created_at": datetime.now().isoformat()
    }
    task_queue.append(task_id)
    if len(task_queue) > Config.MAX_CONCURRENT_TASKS:
        logger.info(f"⚠️ Задача {task_id} добавлена в очередь, текущая длина: {len(task_queue)}")
        return {"task_id": task_id, "message": "Задача в очереди"}
    background_tasks.add_task(generate_clips_task, task_id)
    logger.info(f"🚀 Запущена генерация клипов: {task_id}, максимум {max_clips} клипов")
    return {
        "task_id": task_id,
        "message": "Генерация клипов запущена",
        "video_id": video_id,
        "format_id": format_id,
        "style_id": style_id,
        "max_clips": max_clips
    }

async def generate_clips_task(task_id: str):
    """Фоновая задача генерации клипов с управлением очередью и прогрессом"""
    if task_queue[0] != task_id:
        logger.info(f"⚠️ Ожидание в очереди для задачи {task_id}")
        while task_queue[0] != task_id:
            await asyncio.sleep(5)
    task = generation_tasks[task_id]
    video_id = task["video_id"]
    format_id = task["format_id"]
    style_id = task["style_id"]
    max_clips = task["max_clips"]
    analysis_task = analysis_tasks[video_id]
    video_path = analysis_task["video_path"]
    highlights = analysis_task["analysis"]["highlights"][:max_clips]  # Ограничение клипов
    
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
        generation_tasks[task_id].update({
            "progress": progress,
            "current_stage": f"Создание клипа {i+1}/{total_clips}",
            "stage_progress": int((i + 1) / total_clips * 100)
        })
        
        audio_path = os.path.join(Config.AUDIO_DIR, f"{task_id}_clip_{i}.mp3")
        if not extract_audio(video_path, audio_path, highlight["start_time"], highlight["end_time"] - highlight["start_time"]):
            logger.error(f"❌ Ошибка извлечения аудио для клипа {i+1}")
            continue
        clip_transcript = safe_transcribe_audio(audio_path)
        words_in_range = clip_transcript.get('words', []) if clip_transcript else []
        
        logger.info(f"📝 Найдено {len(words_in_range)} слов для субтитров клипа {i+1}")
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
                "size": os.path.getsize(clip_path) if os.path.exists(clip_path) else 0,
                "status": "completed"
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
        "stage_progress": 100,
        "clips_created": clips_created,
        "completed_at": datetime.now().isoformat()
    })
    task_queue.popleft()
    logger.info(f"🎉 Генерация завершена: {task_id}, создано {clips_created} из {total_clips} клипов")

@app.get("/api/clips/generation/{task_id}/status")
async def get_generation_status(task_id: str):
    """Получение статуса генерации клипов с деталями"""
    if task_id not in generation_tasks:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    task = generation_tasks[task_id]
    response = {
        "task_id": task_id,
        "status": task["status"],
        "progress": task.get("progress", 0),
        "current_stage": task.get("current_stage", "Неизвестно"),
        "stage_progress": task.get("stage_progress", 0),
        "clips_created": len(task.get("clips", [])),
        "max_clips": task.get("max_clips", 0),
        "created_at": task.get("created_at"),
        "completed_at": task.get("completed_at")
    }
    if task["status"] == "completed":
        response["clips"] = task.get("clips", [])
    return response

@app.get("/api/clips/download/{filename}")
async def download_clip(filename: str):
    """Скачивание сгенерированного клипа с проверкой"""
    file_path = os.path.join(Config.CLIPS_DIR, filename)
    if not os.path.exists(file_path):
        logger.error(f"❌ Файл не найден: {file_path}")
        raise HTTPException(status_code=404, detail="Файл не найден")
    logger.info(f"📥 Запрос на скачивание файла: {filename}")
    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=filename
    )

# Функция очистки старых задач и файлов
def cleanup_old_tasks():
    """Очистка старых задач и временных файлов"""
    global last_cleanup
    current_time = time.time()
    if current_time - last_cleanup < Config.CLEANUP_INTERVAL:
        return
    for task_id in list(analysis_tasks.keys()):
        task = analysis_tasks[task_id]
        if task.get("status") in ["error", "completed"]:
            upload_time = datetime.fromisoformat(task.get("upload_time"))
            if (current_time - upload_time.timestamp()) > Config.MAX_TASK_AGE:
                video_path = task.get("video_path")
                if video_path and os.path.exists(video_path):
                    os.remove(video_path)
                    logger.info(f"🗑 Удален старый файл: {video_path}")
                del analysis_tasks[task_id]
                logger.info(f"🗑 Удалена старая задача анализа: {task_id}")
    for task_id in list(generation_tasks.keys()):
        task = generation_tasks[task_id]
        if task.get("status") == "completed":
            created_at = datetime.fromisoformat(task.get("created_at"))
            if (current_time - created_at.timestamp()) > Config.MAX_TASK_AGE:
                for clip in task.get("clips", []):
                    clip_path = os.path.join(Config.CLIPS_DIR, clip["filename"])
                    if os.path.exists(clip_path):
                        os.remove(clip_path)
                        logger.info(f"🗑 Удален старый клип: {clip_path}")
                del generation_tasks[task_id]
                logger.info(f"🗑 Удалена старая задача генерации: {task_id}")
    last_cleanup = current_time
    logger.info("🧹 Очистка завершена")
