# AgentFlow AI Clips v18.4.2 - Полная версия с исправленной поддержкой Supabase
# Система генерации коротких видео клипов с ASS-субтитрами в формате 1080x1920
# Оптимизирована для Render с поддержкой стиля Opus
# Текущая дата и время: 10:37 PM EDT, 13 июля 2025 (воскресенье)

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
import sys

# Импорт зависимостей с подробной обработкой ошибок
try:
    from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
    import openai
    from openai import OpenAI
    from supabase import create_client, Client  # Исправлен импорт Supabase
except ImportError as e:
    print(f"Ошибка импорта модулей: {str(e)}. Убедитесь, что установлены все зависимости (fastapi, uvicorn, openai, supabase-py, psutil).")
    sys.exit(1)

# Настройка детального логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler("agentflow.log")]
)
logger = logging.getLogger("app")
logger.info("Инициализация системы логирования завершена")

# Инициализация FastAPI с полной конфигурацией
app = FastAPI(
    title="AgentFlow AI Clips API",
    description="Генерация клипов с ASS-субтитрами в стиле Opus (1080x1920). Версия 18.4.2.",
    version="18.4.2",
    contact={"name": "Support Team", "email": "support@x.ai", "url": "https://x.ai/support"},
    license_info={"name": "MIT License", "url": "https://opensource.org/licenses/MIT"}
)

# Настройка CORS для всех источников
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "*"]
)
logger.info("CORS настроен для всех источников")

# Основной класс конфигурации
class Config:
    """Глобальные настройки приложения"""
    UPLOAD_DIR = "uploads"  # Директория для загруженных видео
    AUDIO_DIR = "audio"    # Директория для аудио
    CLIPS_DIR = "clips"    # Директория для сгенерированных клипов
    ASS_DIR = "ass_subtitles"  # Директория для субтитров
    FONTS_DIR = "ass_subtitles/fonts"  # Директория для шрифтов
    MAX_FILE_SIZE = 200 * 1024 * 1024  # Максимальный размер файла: 200 MB
    MAX_TASK_AGE = 24 * 60 * 60        # Максимальный возраст задачи: 24 часа
    CLEANUP_INTERVAL = 3600            # Интервал очистки: 1 час
    MAX_CONCURRENT_TASKS = 1           # Максимальное количество параллельных задач

    # Стили субтитров (только Opus)
    ASS_STYLES = {
        "opus": {
            "fontname": "Inter-Bold",  # Используемый шрифт
            "fontsize": 48,           # Размер шрифта
            "primarycolor": "&HFFFFFF",  # Белый цвет текста
            "secondarycolor": "&H00FF00",  # Зеленая подсветка
            "outlinecolor": "&H000000",  # Черный контур
            "backcolor": "&HCC000000",  # Полупрозрачный фон
            "outline": 2,             # Толщина контура
            "shadow": 1,              # Тень
            "alignment": 2,           # Центрирование
            "marginl": 100,           # Левый отступ
            "marginr": 100,           # Правый отступ
            "marginv": 1700,          # Вертикальный отступ
            "borderstyle": 1,         # Стиль границы
            "scalex": 100,            # Масштаб по X
            "scaley": 100,            # Масштаб по Y
            "spacing": 0,             # Интервал между символами
            "angle": 0                # Угол наклона
        }
    }

# Создание директорий с проверками
for directory in [Config.UPLOAD_DIR, Config.AUDIO_DIR, Config.CLIPS_DIR, Config.ASS_DIR, Config.FONTS_DIR]:
    os.makedirs(directory, exist_ok=True)
    logger.debug(f"Директория {directory} создана или проверена")

# Глобальные переменные
analysis_tasks = {}  # Хранилище задач анализа видео
generation_tasks = {}  # Хранилище задач генерации клипов
task_queue = deque(maxlen=Config.MAX_CONCURRENT_TASKS)  # Очередь задач
cache = {}  # Кэш для транскрибации
last_cleanup = time.time()  # Время последней очистки

# Инициализация OpenAI с проверкой
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    logger.error("Переменная OPENAI_API_KEY не найдена в окружении")
    sys.exit(1)
client = OpenAI(api_key=openai_api_key)
logger.info("Клиент OpenAI успешно инициализирован")

# Инициализация Supabase
supabase: Client = None
service_supabase: Client = None
SUPABASE_BUCKET = "video-results"

def init_supabase() -> bool:
    """Инициализация подключения к Supabase"""
    global supabase, service_supabase
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")
        supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not all([supabase_url, supabase_anon_key, supabase_service_key]):
            logger.warning("Не все переменные Supabase заданы, локальное хранение будет использовано")
            return False
        supabase = create_client(supabase_url, supabase_anon_key)
        service_supabase = create_client(supabase_url, supabase_service_key)
        logger.info("Подключение к Supabase установлено")
        return True
    except Exception as e:
        logger.error(f"Ошибка инициализации Supabase: {str(e)}")
        return False

supabase_available = init_supabase()
logger.info(f"Supabase доступен: {supabase_available}")

# Модели Pydantic для валидации
class VideoAnalysisRequest(BaseModel):
    """Запрос на анализ видео"""
    video_id: str
    retry_count: Optional[int] = 0

class ClipGenerationRequest(BaseModel):
    """Запрос на генерацию клипов"""
    video_id: str
    format_id: str
    style_id: str = "opus"
    max_clips: Optional[int] = 3

class VideoInfo(BaseModel):
    """Информация о видео"""
    id: str
    filename: str
    duration: float
    size: int
    status: str
    upload_time: str

class ClipInfo(BaseModel):
    """Информация о клипе"""
    id: str
    video_id: str
    format_id: str
    style_id: str
    status: str
    progress: int
    download_url: Optional[str] = None

# Утилиты
def upload_clip_to_supabase(local_path: str, filename: str) -> Optional[str]:
    """Загрузка клипа в Supabase или возврат локального пути"""
    if not supabase_available or not service_supabase:
        logger.warning("Supabase недоступен, используется локальный путь")
        return f"/api/clips/download/{filename}"
    try:
        with open(local_path, 'rb') as file:
            file_content = file.read()
        storage_path = f"clips/{datetime.now().strftime('%Y%m%d')}/{filename}"
        response = service_supabase.storage.from_(SUPABASE_BUCKET).upload(storage_path, file_content)
        if response:
            public_url = service_supabase.storage.from_(SUPABASE_BUCKET).get_public_url(storage_path)
            logger.info(f"Клип загружен в Supabase: {public_url}")
            return public_url
    except Exception as e:
        logger.error(f"Ошибка загрузки в Supabase: {str(e)}")
    logger.warning("Возврат к локальному хранению из-за ошибки")
    return f"/api/clips/download/{filename}"

def get_video_duration(video_path: str) -> float:
    """Получение длительности видео с помощью ffprobe"""
    try:
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        data = json.loads(result.stdout)
        duration = float(data['format']['duration'])
        logger.debug(f"Длительность видео {video_path}: {duration} секунд")
        return duration
    except Exception as e:
        logger.error(f"Ошибка получения длительности видео: {str(e)}")
        return 60.0  # Значение по умолчанию

def ffmpeg_available_codecs() -> List[str]:
    """Проверка доступных кодеков FFmpeg"""
    try:
        result = subprocess.run(['ffmpeg', '-codecs'], capture_output=True, text=True, timeout=10)
        codecs = [line.split()[1] for line in result.stdout.splitlines() if 'h264_nvenc' in line]
        logger.info(f"Найдены кодеки FFmpeg: {codecs}")
        return codecs
    except Exception as e:
        logger.warning(f"Ошибка проверки кодеков FFmpeg: {str(e)}")
        return []

def extract_audio(video_path: str, audio_path: str, start_time: float = 0, duration: float = None) -> bool:
    """Извлечение аудио из видео"""
    try:
        cmd = ['ffmpeg', '-i', video_path, '-vn', '-acodec', 'mp3', '-ar', '16000', '-ac', '1', '-y', audio_path]
        if start_time:
            cmd.extend(['-ss', str(start_time)])
        if duration:
            cmd.extend(['-t', str(duration)])
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
        if os.path.exists(audio_path):
            logger.info(f"Аудио успешно извлечено: {audio_path}")
            return True
        else:
            logger.error(f"Аудио не создано: {audio_path}")
            return False
    except subprocess.TimeoutExpired as te:
        logger.error(f"Таймаут при извлечении аудио: {str(te)}")
        return False
    except Exception as e:
        logger.error(f"Ошибка извлечения аудио: {str(e)}")
        return False

def safe_transcribe_audio(audio_path: str) -> Optional[Dict]:
    """Транскрибация аудио с кэшированием"""
    cache_key = f"transcribe_{hash(open(audio_path, 'rb').read())}"
    if cache_key in cache:
        logger.info(f"Использование кэшированной транскрибации для {cache_key}")
        return cache[cache_key]
    try:
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["word"]
            )
            result = transcript.model_dump() if hasattr(transcript, 'model_dump') else dict(transcript)
            cache[cache_key] = result
            logger.info(f"Транскрибация завершена: {len(result.get('words', []))} слов")
            return result
    except Exception as e:
        logger.error(f"Ошибка транскрибации: {str(e)}")
        return None

def analyze_with_chatgpt(transcript_text: str, video_duration: float) -> Optional[Dict]:
    """Анализ транскрипта с ChatGPT"""
    try:
        target_clips = 2 if video_duration <= 30 else 3 if video_duration <= 60 else 4
        prompt = f"Проанализируй транскрипт видео ({video_duration:.1f}s). Найди {target_clips} интересных моментов (15-20s). Верни JSON с 'highlights' и объектами {{start_time, end_time, title, description}}."
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.7
        )
        content = response.choices[0].message.content.strip()
        if content.startswith('```json'):
            content = content[7:-3].strip()
        result = json.loads(content)
        logger.info(f"Анализ ChatGPT завершен: {len(result['highlights'])} клипов")
        return result
    except Exception as e:
        logger.error(f"Ошибка анализа с ChatGPT: {str(e)}")
        return {"highlights": [{"start_time": 0, "end_time": 20, "title": "Резервный клип", "description": "Резерв"}]}

# Система субтитров
class ASSKaraokeSubtitleSystem:
    """Генерация ASS-файлов с динамической подсветкой"""
    def __init__(self):
        self.styles = Config.ASS_STYLES
        self.font_path = os.path.join(Config.FONTS_DIR, "Inter-Bold.ttf")
        if not os.path.exists(self.font_path):
            logger.warning(f"Шрифт {self.font_path} не найден, используется системный")

    def generate_ass_file(self, words_data: List[Dict], style: str = "opus", video_duration: float = 10.0) -> str:
        """Создание ASS-файла с субтитрами"""
        style_config = self.styles.get(style, self.styles["opus"])
        ass_filename = f"subtitles_{uuid.uuid4().hex[:8]}.ass"
        ass_path = os.path.join(Config.ASS_DIR, ass_filename)
        
        ass_content = "[Script Info]\n"
        ass_content += "Title: AgentFlow AI Clips Subtitles\n"
        ass_content += "ScriptType: v4.00+\n"
        ass_content += "WrapStyle: 2\n"
        ass_content += "PlayResX: 1080\n"
        ass_content += "PlayResY: 1920\n"
        ass_content += "ScaledBorderAndShadow: yes\n"
        if os.path.exists(self.font_path):
            ass_content += f"FontFile: {self.font_path}\n"
        ass_content += "\n[V4+ Styles]\n"
        ass_content += "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Outline, Shadow, Alignment\n"
        ass_content += (f"Style: Default,{style_config['fontname']},{style_config['fontsize']},"
                       f"{style_config['primarycolor']},{style_config['secondarycolor']},"
                       f"{style_config['outlinecolor']},{style_config['backcolor']},"
                       f"{style_config['outline']},{style_config['shadow']},{style_config['alignment']}\n\n")
        
        ass_content += "[Events]\n"
        ass_content += "Format: Layer, Start, End, Style, Text\n"
        
        total_words = len(words_data)
        for i, word_data in enumerate(words_data):
            start_time = self._seconds_to_ass_time(word_data['start'])
            end_time = self._seconds_to_ass_time(word_data['end'])
            word = word_data['word'].strip()
            if word:
                duration = max(50, min(500, int((word_data['end'] - word_data['start']) * 1000)))
                ass_content += (f"Dialogue: 0,{start_time},{end_time},Default,"
                               f"{{pos(540,1700)}}{{\t(0,{duration},\c&H00FF00&)}}{word}{{\t({duration},0,\c&HFFFFFF&)}}\n")
                logger.debug(f"Сгенерирован субтитр для слова '{word}' ({i+1}/{total_words})")
        
        with open(ass_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        logger.info(f"ASS-файл создан: {ass_path}, слов: {total_words}")
        return ass_path
    
    def _seconds_to_ass_time(self, seconds: float) -> str:
        """Конвертация секунд в формат времени ASS"""
        if seconds < 0:
            logger.warning(f"Отрицательное время: {seconds}, заменено на 0")
            seconds = 0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centiseconds = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

ass_subtitle_system = ASSKaraokeSubtitleSystem()
logger.info("Система субтитров инициализирована")

def create_clip_with_ass_subtitles(video_path: str, start_time: float, end_time: float, words_data: List[Dict], output_path: str, format_type: str = "9:16", style: str = "opus") -> bool:
    """Создание клипа с наложением субтитров"""
    try:
        logger.info(f"Начало создания клипа: {start_time}-{end_time}s, стиль: {style}")
        clip_duration = end_time - start_time
        if clip_duration <= 0:
            logger.error(f"Неверная длительность клипа: {clip_duration}s")
            return False
        
        # Фильтрация слов для клипа
        clip_words = []
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
                    logger.debug(f"Слово '{word_data['word']}' добавлено: {clip_word_start:.2f}s-{clip_word_end:.2f}s")
        
        logger.info(f"Найдено {len(clip_words)} слов для субтитров")
        temp_video_path = output_path.replace('.mp4', '_temp.mp4')
        
        # Выбор кодека
        nvenc_available = 'h264_nvenc' in ffmpeg_available_codecs()
        codec = 'h264_nvenc' if nvenc_available else 'libx264'
        logger.info(f"Используемый кодек: {codec}")
        
        # ЭТАП 1: Создание базового видео
        base_cmd = [
            'ffmpeg', '-i', video_path, '-ss', str(start_time), '-t', str(clip_duration),
            '-vf', 'scale=1080:1920,crop=1080:1920:0:0', '-c:v', codec, '-preset', 'ultrafast',
            '-c:a', 'aac', '-b:a', '64k', '-y', temp_video_path
        ]
        logger.info("ЭТАП 1: Запуск создания базового видео")
        result = subprocess.run(base_cmd, capture_output=True, text=True, check=True, timeout=120)
        if result.returncode != 0:
            logger.error(f"ЭТАП 1 завершен с ошибкой: {result.stderr}")
            return False
        logger.info("ЭТАП 1 завершен: базовое видео создано")
        
        # ЭТАП 2: Наложение субтитров
        if clip_words:
            logger.info("ЭТАП 2: Генерация и наложение ASS-субтитров")
            ass_path = ass_subtitle_system.generate_ass_file(clip_words, style, clip_duration)
            if not os.path.exists(ass_path):
                logger.error(f"ASS-файл не создан: {ass_path}")
                os.rename(temp_video_path, output_path)
                return True
            subtitle_cmd = [
                'ffmpeg', '-i', temp_video_path, '-vf', f'ass={ass_path}', '-c:v', codec,
                '-preset', 'ultrafast', '-c:a', 'copy', '-y', output_path
            ]
            logger.info("Применение ASS-субтитров к видео")
            result = subprocess.run(subtitle_cmd, capture_output=True, text=True, check=True, timeout=120)
            if result.returncode != 0:
                logger.error(f"ЭТАП 2 завершен с ошибкой: {result.stderr}")
                os.rename(temp_video_path, output_path)
                return True
            logger.info("ЭТАП 2 завершен: субтитры наложены")
            os.remove(ass_path)
        else:
            logger.info("Нет слов для субтитров, копирование базового видео")
            os.rename(temp_video_path, output_path)
        
        # ЭТАП 3: Очистка
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
            logger.info("Временные файлы удалены")
        logger.info(f"Клип создан: {output_path}, длительность: {clip_duration}s")
        return True
    except subprocess.TimeoutExpired as te:
        logger.error(f"Таймаут при создании клипа: {str(te)}")
        if os.path.exists(temp_video_path):
            os.rename(temp_video_path, output_path)
        return False
    except Exception as e:
        logger.error(f"Общая ошибка создания клипа: {str(e)}")
        if os.path.exists(temp_video_path):
            os.rename(temp_video_path, output_path)
        return False

def check_memory_available() -> bool:
    """Проверка доступной памяти"""
    memory = psutil.virtual_memory()
    available_mb = memory.available / (1024 * 1024)
    logger.debug(f"Доступно памяти: {available_mb:.1f} MB из {memory.total / (1024 * 1024):.1f} MB")
    return memory.available > 50 * 1024 * 1024

# Эндпоинты
@app.get("/")
async def root():
    """Основной эндпоинт для проверки статуса"""
    logger.info("Запрос на корневой эндпоинт")
    return {"message": "AgentFlow AI Clips v18.4.2", "status": "running", "timestamp": datetime.now().isoformat()}

@app.get("/health")
async def health_check():
    """Проверка состояния системы"""
    logger.info("Запрос на проверку состояния")
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    return {
        "status": "healthy",
        "version": "18.4.2",
        "timestamp": datetime.now().isoformat(),
        "memory_usage": f"{memory.percent}% ({memory.available / (1024 * 1024):.1f} MB доступно)",
        "disk_usage": f"{disk.percent}%"
    }

@app.post("/api/videos/upload")
async def upload_video(file: UploadFile = File(...)):
    """Загрузка видео файла"""
    logger.info(f"Получен запрос на загрузку файла: {file.filename}")
    if not check_memory_available():
        logger.error("Недостаточно памяти для загрузки")
        raise HTTPException(status_code=503, detail="Недостаточно памяти")
    if file.size and file.size > Config.MAX_FILE_SIZE:
        logger.error(f"Файл {file.filename} превышает лимит {Config.MAX_FILE_SIZE / (1024 * 1024)} MB")
        raise HTTPException(status_code=413, detail="Файл слишком большой")
    video_id = str(uuid.uuid4())
    video_path = os.path.join(Config.UPLOAD_DIR, f"{video_id}.mp4")
    try:
        with open(video_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        duration = get_video_duration(video_path)
        analysis_tasks[video_id] = {
            "video_id": video_id,
            "video_path": video_path,
            "duration": duration,
            "size": len(content),
            "status": "uploaded",
            "upload_time": datetime.now().isoformat()
        }
        logger.info(f"Видео загружено: {video_id}, размер: {len(content)/1024/1024:.1f} MB")
        return {
            "video_id": video_id,
            "filename": file.filename,
            "duration": duration,
            "size": len(content),
            "status": "uploaded"
        }
    except Exception as e:
        logger.error(f"Ошибка загрузки видео: {str(e)}")
        if os.path.exists(video_path):
            os.remove(video_path)
        raise HTTPException(status_code=500, detail="Ошибка при загрузке")

@app.post("/api/videos/analyze")
async def analyze_video(request: VideoAnalysisRequest, background_tasks: BackgroundTasks):
    """Запуск анализа видео"""
    logger.info(f"Запуск анализа для видео: {request.video_id}")
    video_id = request.video_id
    if video_id not in analysis_tasks or not check_memory_available():
        logger.error(f"Видео {video_id} не найдено или недостаточно памяти")
        raise HTTPException(status_code=404, detail="Видео не найдено")
    background_tasks.add_task(analyze_video_task, video_id)
    analysis_tasks[video_id]["status"] = "analyzing"
    logger.info(f"Анализ запущен для {video_id}")
    return {"message": "Анализ запущен", "video_id": video_id}

async def analyze_video_task(video_id: str):
    """Фоновая задача анализа видео"""
    logger.info(f"Начало анализа видео: {video_id}")
    task = analysis_tasks[video_id]
    video_path = task["video_path"]
    duration = task["duration"]
    audio_path = os.path.join(Config.AUDIO_DIR, f"{video_id}.mp3")
    if not extract_audio(video_path, audio_path):
        logger.error(f"Ошибка извлечения аудио для {video_id}")
        task["status"] = "error"
        return
    transcript = safe_transcribe_audio(audio_path)
    if not transcript:
        logger.error(f"Ошибка транскрибации для {video_id}")
        task["status"] = "error"
        return
    analysis = analyze_with_chatgpt(transcript.get("text", ""), duration)
    task.update({
        "status": "completed",
        "transcript": transcript,
        "analysis": analysis,
        "completed_at": datetime.now().isoformat()
    })
    logger.info(f"Анализ завершен для {video_id}, найдено {len(analysis.get('highlights', []))} клипов")

@app.get("/api/videos/{video_id}/status")
async def get_video_status(video_id: str):
    """Получение статуса анализа видео"""
    logger.info(f"Запрос статуса для видео: {video_id}")
    if video_id not in analysis_tasks:
        logger.error(f"Видео {video_id} не найдено")
        raise HTTPException(status_code=404, detail="Видео не найдено")
    task = analysis_tasks[video_id]
    response = {
        "video_id": video_id,
        "status": task["status"],
        "duration": task.get("duration", 0.0),
        "size": task.get("size", 0),
        "upload_time": task.get("upload_time")
    }
    if task["status"] == "completed":
        response["analysis"] = task.get("analysis", {})
    elif task["status"] == "error":
        response["error"] = "Произошла ошибка при анализе"
    return response

@app.post("/api/clips/generate")
async def generate_clips(request: ClipGenerationRequest, background_tasks: BackgroundTasks):
    """Запуск генерации клипов"""
    logger.info(f"Запуск генерации клипов для видео: {request.video_id}")
    if not check_memory_available():
        logger.error("Недостаточно памяти для генерации")
        raise HTTPException(status_code=503, detail="Недостаточно памяти")
    video_id = request.video_id
    format_id = request.format_id
    style_id = request.style_id
    max_clips = min(request.max_clips, 5)
    if video_id not in analysis_tasks or analysis_tasks[video_id]["status"] != "completed":
        logger.error(f"Анализ для {video_id} не завершен")
        raise HTTPException(status_code=400, detail="Анализ не завершен")
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
    if len(task_queue) == 1:
        background_tasks.add_task(generate_clips_task, task_id)
    logger.info(f"Генерация запущена: {task_id}, максимум {max_clips} клипов")
    return {
        "task_id": task_id,
        "message": "Генерация клипов запущена",
        "video_id": video_id,
        "format_id": format_id,
        "style_id": style_id,
        "max_clips": max_clips
    }

async def generate_clips_task(task_id: str):
    """Фоновая задача генерации клипов"""
    logger.info(f"Начало генерации для задачи: {task_id}")
    if task_queue[0] != task_id:
        logger.info(f"Задача {task_id} ожидает в очереди")
        while task_queue[0] != task_id:
            await asyncio.sleep(5)
    task = generation_tasks[task_id]
    video_id = task["video_id"]
    format_id = task["format_id"]
    style_id = task["style_id"]
    max_clips = task["max_clips"]
    video_path = analysis_tasks[video_id]["video_path"]
    highlights = analysis_tasks[video_id].get("analysis", {}).get("highlights", [])[:max_clips]
    
    task["status"] = "generating"
    logger.info(f"Генерация {len(highlights)} клипов для {task_id}")
    clips_created = 0
    total_clips = len(highlights)
    
    for i, highlight in enumerate(highlights):
        if not check_memory_available():
            logger.warning("Недостаточно памяти, прерывание генерации")
            break
        logger.info(f"Создание клипа {i+1}/{total_clips}: {highlight['start_time']}-{highlight['end_time']}s")
        task["progress"] = int((i / total_clips) * 100)
        task["current_stage"] = f"Клип {i+1}/{total_clips}"
        
        audio_path = os.path.join(Config.AUDIO_DIR, f"{task_id}_clip_{i}.mp3")
        if not extract_audio(video_path, audio_path, highlight["start_time"], highlight["end_time"] - highlight["start_time"]):
            logger.error(f"Ошибка извлечения аудио для клипа {i+1}")
            continue
        transcript = safe_transcribe_audio(audio_path)
        words_in_range = transcript.get("words", []) if transcript else []
        
        logger.info(f"Найдено {len(words_in_range)} слов для клипа {i+1}")
        clip_filename = f"{task_id}_clip_{i+1}_{format_id.replace(':', 'x')}.mp4"
        clip_path = os.path.join(Config.CLIPS_DIR, clip_filename)
        
        if create_clip_with_ass_subtitles(video_path, highlight["start_time"], highlight["end_time"], words_in_range, clip_path, format_id, style_id):
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
                "size": os.path.getsize(clip_path)
            }
            task["clips"].append(clip_info)
            clips_created += 1
            logger.info(f"Клип {i+1} создан: {clip_filename}")
        else:
            logger.error(f"Ошибка создания клипа {i+1}")
    
    task.update({
        "status": "completed",
        "progress": 100,
        "current_stage": "Завершено",
        "clips_created": clips_created,
        "completed_at": datetime.now().isoformat()
    })
    task_queue.popleft()
    logger.info(f"Генерация завершена: {task_id}, создано {clips_created} клипов")

@app.get("/api/clips/generation/{task_id}/status")
async def get_generation_status(task_id: str):
    """Получение статуса генерации"""
    logger.info(f"Запрос статуса генерации для {task_id}")
    if task_id not in generation_tasks:
        logger.error(f"Задача {task_id} не найдена")
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return generation_tasks[task_id]

@app.get("/api/clips/download/{filename}")
async def download_clip(filename: str):
    """Скачивание клипа"""
    logger.info(f"Запрос на скачивание файла: {filename}")
    file_path = os.path.join(Config.CLIPS_DIR, filename)
    if not os.path.exists(file_path):
        logger.error(f"Файл {filename} не найден")
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(file_path, media_type="video/mp4", filename=filename)

def cleanup_old_tasks():
    """Очистка старых задач и файлов"""
    logger.info("Запуск очистки старых задач")
    global last_cleanup
    current_time = time.time()
    if current_time - last_cleanup < Config.CLEANUP_INTERVAL:
        logger.debug("Очистка не требуется, интервал не истек")
        return
    for task_id in list(analysis_tasks.keys()):
        task = analysis_tasks[task_id]
        if task["status"] in ["error", "completed"]:
            upload_time = datetime.fromisoformat(task["upload_time"])
            if current_time - upload_time.timestamp() > Config.MAX_TASK_AGE:
                if os.path.exists(task["video_path"]):
                    os.remove(task["video_path"])
                    logger.info(f"Удален старый файл: {task['video_path']}")
                del analysis_tasks[task_id]
                logger.info(f"Удалена старая задача анализа: {task_id}")
    for task_id in list(generation_tasks.keys()):
        task = generation_tasks[task_id]
        if task["status"] == "completed":
            created_at = datetime.fromisoformat(task["created_at"])
            if current_time - created_at.timestamp() > Config.MAX_TASK_AGE:
                for clip in task.get("clips", []):
                    clip_path = os.path.join(Config.CLIPS_DIR, clip["filename"])
                    if os.path.exists(clip_path):
                        os.remove(clip_path)
                        logger.info(f"Удален старый клип: {clip_path}")
                del generation_tasks[task_id]
                logger.info(f"Удалена старая задача генерации: {task_id}")
    last_cleanup = current_time
    logger.info("Очистка завершена")

if __name__ == "__main__":
    import uvicorn
    logger.info("Запуск AgentFlow AI Clips v18.4.2")
    logger.info("Система готова к работе с субтитрами в стиле Opus")
    logger.info("GPU-ускорение доступно при наличии h264_nvenc")
    port = int(os.getenv("PORT", 10000))
    try:
        while True:
            cleanup_old_tasks()
            uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    except KeyboardInterrupt:
        logger.info("Приложение завершено пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}")
