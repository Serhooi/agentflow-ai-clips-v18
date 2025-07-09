#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AgentFlow AI Clips API v21.0.0
Оптимизированная версия с Whisper.cpp и системой очередей
"""

import os
import json
import uuid
import time
import logging
import asyncio
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Any, Union

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("app")

# Загрузка переменных окружения
from dotenv import load_dotenv
load_dotenv()

# OpenAI для анализа контента
from openai import OpenAI

# Faster-Whisper (Whisper.cpp) для транскрибации
from faster_whisper import WhisperModel

# Supabase (опционально)
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
    logger.info("📦 Supabase доступен (опционально)")
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("⚠️ Supabase не установлен - используется локальное хранение")

# Инициализация FastAPI
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(
    title="AgentFlow AI Clips API",
    description="Профессиональная система генерации коротких клипов с оптимизированной обработкой",
    version="21.0.0"
)

# CORS настройки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Директории для хранения файлов
UPLOAD_DIR = "uploads"
AUDIO_DIR = "audio"
RESULTS_DIR = "results"
CLIPS_DIR = "clips"

# Создаем директории если не существуют
for dir_path in [UPLOAD_DIR, AUDIO_DIR, RESULTS_DIR, CLIPS_DIR]:
    os.makedirs(dir_path, exist_ok=True)

# Инициализация OpenAI
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)
logger.info("✅ OpenAI клиент инициализирован")

# Инициализация Supabase
supabase = None
service_supabase = None
SUPABASE_BUCKET = "video-results"

# Глобальная модель Whisper.cpp
whisper_model = None

# Система очередей
processing_semaphore = asyncio.Semaphore(1)  # Ограничиваем до 1 одновременной обработки
task_queue = {}  # Очередь задач
task_status = {}  # Статусы задач

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
        
        if not all([supabase_url, supabase_anon_key]):
            logger.warning("⚠️ Не все обязательные Supabase переменные настроены")
            logger.info(f"SUPABASE_URL: {'✅' if supabase_url else '❌'}")
            logger.info(f"SUPABASE_ANON_KEY: {'✅' if supabase_anon_key else '❌'}")
            logger.info(f"SUPABASE_SERVICE_ROLE_KEY: {'✅' if supabase_service_key else '❌'}")
            return False
        
        # Основной клиент - максимально простая инициализация для v1.0.4
        supabase = create_client(supabase_url, supabase_anon_key)
        
        # Service role клиент для загрузки файлов (если доступен)
        if supabase_service_key:
            service_supabase = create_client(supabase_url, supabase_service_key)
        else:
            service_supabase = supabase  # Используем основной клиент
        
        logger.info("✅ Supabase Storage подключен")
        logger.info(f"📍 URL: {supabase_url}")
        logger.info(f"📦 Версия: supabase==1.0.4 (стабильная)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Supabase: {e}")
        logger.error(f"Тип ошибки: {type(e).__name__}")
        # Продолжаем работу без Supabase
        return False

# Инициализация Supabase при запуске
supabase_available = init_supabase()

@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске приложения"""
    global whisper_model
    
    try:
        # Загружаем модель один раз при старте
        logger.info("🔄 Загрузка Whisper.cpp модели...")
        whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        logger.info("✅ Whisper.cpp модель загружена успешно")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки Whisper.cpp модели: {e}")
    
    logger.info("🚀 AgentFlow AI Clips v21.0.0 started!")
    logger.info("🎬 Whisper.cpp + очередь задач активированы")
    logger.info("🔥 Оптимизировано для Render.com")
    logger.info("⚡ Стабильная обработка видео")

# Pydantic модели
class VideoAnalysisRequest(BaseModel):
    video_id: str

class ClipGenerationRequest(BaseModel):
    video_id: str
    format_id: str
    style_id: str = "modern"
    highlight_index: int = 0  # Индекс highlight для генерации (0-4)

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

def get_audio_duration(audio_path: str) -> float:
    """Получение длительности аудио"""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json', 
            '-show_format', audio_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data['format']['duration'])
    except Exception as e:
        logger.error(f"Ошибка получения длительности аудио: {e}")
        return 60.0  # Fallback

async def transcribe_audio(audio_path: str) -> dict:
    """Транскрибация аудио с Whisper.cpp"""
    global whisper_model
    
    try:
        # Проверяем длительность аудио
        audio_duration = get_audio_duration(audio_path)
        if audio_duration > 600:  # Ограничение 10 минут
            logger.warning(f"⚠️ Аудио слишком длинное: {audio_duration} секунд")
            return {"error": "Audio too long", "segments": []}
        
        # Проверяем, что модель загружена
        if whisper_model is None:
            logger.error("❌ Whisper.cpp модель не загружена")
            return {"error": "Whisper model not loaded", "segments": []}
        
        logger.info("🔄 Транскрибация с Whisper.cpp...")
        
        # Транскрибация с обработкой ошибок
        segments, info = whisper_model.transcribe(
            audio_path, 
            beam_size=1, 
            word_timestamps=True,
            max_initial_timestamp=audio_duration
        )
        
        # Форматирование результата в нужный JSON
        result = {"segments": []}
        for segment in segments:
            words = [{"word": w.word, "start": w.start, "end": w.end} for w in segment.words]
            result["segments"].append({
                "text": segment.text,
                "start": segment.start,
                "end": segment.end,
                "words": words
            })
        
        logger.info(f"✅ Whisper.cpp транскрибация завершена: {len(result['segments'])} сегментов")
        return result
    
    except Exception as e:
        logger.error(f"❌ Ошибка транскрибации: {e}")
        # Возвращаем структуру с ошибкой, но сохраняем формат
        return {"error": str(e), "segments": []}

async def analyze_with_chatgpt(transcript_text: str, video_duration: float) -> Optional[Dict]:
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
    """Создание равномерно распределенных клипов при ошибке"""
    highlights = []
    
    # Определяем длительность клипа и интервал между клипами
    clip_duration = min(20.0, video_duration / target_clips)
    interval = (video_duration - (clip_duration * target_clips)) / (target_clips + 1)
    
    # Создаем равномерно распределенные клипы
    for i in range(target_clips):
        start_time = interval * (i + 1) + clip_duration * i
        end_time = start_time + clip_duration
        
        highlights.append({
            "start_time": start_time,
            "end_time": end_time,
            "title": f"Клип {i + 1}",
            "description": f"Автоматически созданный клип {i + 1}",
            "keywords": []
        })
    
    return {"highlights": highlights}

async def process_video(video_id: str) -> dict:
    """Обработка видео с транскрибацией и анализом"""
    try:
        # Пути к файлам
        video_path = os.path.join(UPLOAD_DIR, f"{video_id}.mp4")
        audio_path = os.path.join(AUDIO_DIR, f"{video_id}.mp3")
        
        # Проверяем существование видео
        if not os.path.exists(video_path):
            logger.error(f"❌ Видео не найдено: {video_path}")
            return {"error": "Video not found"}
        
        # Получаем длительность видео
        video_duration = get_video_duration(video_path)
        
        # Извлекаем аудио
        logger.info("🔄 Извлечение аудио из видео...")
        if not extract_audio(video_path, audio_path):
            logger.error("❌ Ошибка извлечения аудио")
            return {"error": "Audio extraction failed"}
        
        logger.info(f"🎵 Аудио извлечено: {audio_path}")
        
        # Транскрибация аудио
        logger.info("🔄 Транскрибация аудио...")
        transcript = await transcribe_audio(audio_path)
        
        if "error" in transcript and not transcript.get("segments"):
            logger.error(f"❌ Ошибка транскрибации: {transcript['error']}")
            return {"error": transcript["error"]}
        
        # Сохраняем транскрипт
        transcript_path = os.path.join(RESULTS_DIR, f"{video_id}_transcript.json")
        with open(transcript_path, 'w', encoding='utf-8') as f:
            json.dump(transcript, f, ensure_ascii=False, indent=2)
        
        # Подготавливаем текст для анализа
        transcript_text = " ".join([segment["text"] for segment in transcript["segments"]])
        
        # Анализ с ChatGPT
        logger.info("🔄 Анализ транскрипта с ChatGPT...")
        analysis = await analyze_with_chatgpt(transcript_text, video_duration)
        
        if not analysis or "error" in analysis:
            logger.error(f"❌ Ошибка анализа: {analysis.get('error', 'Unknown error')}")
            # Используем fallback
            analysis = create_fallback_highlights(video_duration, 3)
        
        # Сохраняем анализ
        analysis_path = os.path.join(RESULTS_DIR, f"{video_id}_analysis.json")
        with open(analysis_path, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
        
        # Возвращаем результат
        logger.info(f"✅ Анализ видео завершен: {video_id}")
        logger.info(f"✅ Обработка видео {video_id} завершена успешно")
        
        return {
            "transcript": transcript,
            "highlights": analysis.get("highlights", [])
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки видео: {e}")
        return {"error": str(e)}

async def process_video_task(video_id: str):
    """Задача обработки видео для очереди"""
    # Обновляем статус
    task_status[video_id] = {
        "status": "processing",
        "progress": 10,
        "message": "Начало обработки видео"
    }
    
    try:
        # Получаем семафор для ограничения параллельной обработки
        async with processing_semaphore:
            logger.info(f"🔄 Начало обработки видео из очереди: {video_id}")
            
            # Обновляем статус
            task_status[video_id] = {
                "status": "processing",
                "progress": 20,
                "message": "Извлечение аудио из видео..."
            }
            
            # Обрабатываем видео
            result = await process_video(video_id)
            
            if "error" in result:
                # Обновляем статус с ошибкой
                task_status[video_id] = {
                    "status": "error",
                    "progress": 100,
                    "message": f"Ошибка: {result['error']}"
                }
                logger.error(f"❌ Ошибка обработки видео {video_id}: {result['error']}")
            else:
                # Обновляем статус с успехом
                task_status[video_id] = {
                    "status": "completed",
                    "progress": 100,
                    "message": "Обработка завершена успешно",
                    "result": result
                }
                logger.info(f"✅ Обработка видео {video_id} завершена успешно")
    
    except Exception as e:
        # Обновляем статус с ошибкой
        task_status[video_id] = {
            "status": "error",
            "progress": 100,
            "message": f"Ошибка: {str(e)}"
        }
        logger.error(f"❌ Ошибка в задаче обработки видео {video_id}: {e}")

@app.post("/api/videos/upload")
async def upload_video(file: UploadFile = File(...)):
    """Загрузка видео"""
    try:
        # Генерируем уникальный ID
        video_id = str(uuid.uuid4())
        
        # Путь для сохранения
        video_path = os.path.join(UPLOAD_DIR, f"{video_id}.mp4")
        
        # Сохраняем файл
        with open(video_path, "wb") as buffer:
            buffer.write(await file.read())
        
        # Получаем информацию о видео
        file_size = os.path.getsize(video_path)
        duration = get_video_duration(video_path)
        
        logger.info(f"📁 Получен файл: {file.filename} ({file_size / 1024 / 1024:.1f} MB)")
        logger.info(f"✅ Видео загружено: {video_id}, длительность: {duration:.1f}s")
        
        # Возвращаем информацию
        return {
            "video_id": video_id,
            "filename": file.filename,
            "duration": duration,
            "size": file_size,
            "upload_time": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки видео: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/videos/analyze")
async def analyze_video(request: VideoAnalysisRequest, background_tasks: BackgroundTasks):
    """Анализ видео с транскрибацией"""
    video_id = request.video_id
    
    # Проверяем существование видео
    video_path = os.path.join(UPLOAD_DIR, f"{video_id}.mp4")
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Проверяем, не обрабатывается ли уже видео
    if video_id in task_status:
        status = task_status[video_id]["status"]
        if status == "processing":
            return {"status": "processing", "message": "Видео уже обрабатывается"}
        elif status == "completed":
            return {"status": "completed", "message": "Видео уже обработано"}
    
    # Добавляем в очередь
    logger.info(f"🔍 Начинаю анализ видео: {video_id}")
    
    # Инициализируем статус
    task_status[video_id] = {
        "status": "queued",
        "progress": 0,
        "message": "В очереди на обработку"
    }
    
    # Запускаем задачу в фоне
    background_tasks.add_task(process_video_task, video_id)
    
    return {"status": "queued", "video_id": video_id, "message": "Видео добавлено в очередь на обработку"}

@app.get("/api/videos/{video_id}/status")
async def get_video_status(video_id: str):
    """Получение статуса обработки видео"""
    # Проверяем существование видео
    video_path = os.path.join(UPLOAD_DIR, f"{video_id}.mp4")
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Проверяем статус в очереди
    if video_id not in task_status:
        # Проверяем, есть ли сохраненные результаты
        transcript_path = os.path.join(RESULTS_DIR, f"{video_id}_transcript.json")
        analysis_path = os.path.join(RESULTS_DIR, f"{video_id}_analysis.json")
        
        if os.path.exists(transcript_path) and os.path.exists(analysis_path):
            # Загружаем результаты
            with open(transcript_path, 'r', encoding='utf-8') as f:
                transcript = json.load(f)
            
            with open(analysis_path, 'r', encoding='utf-8') as f:
                analysis = json.load(f)
            
            # Создаем статус с результатами
            task_status[video_id] = {
                "status": "completed",
                "progress": 100,
                "message": "Обработка завершена успешно",
                "result": {
                    "transcript": transcript,
                    "highlights": analysis.get("highlights", [])
                }
            }
        else:
            # Нет информации о задаче
            return {
                "status": "unknown",
                "video_id": video_id,
                "message": "Видео не обрабатывалось или информация о задаче утеряна"
            }
    
    # Получаем текущий статус
    status_data = task_status[video_id]
    
    # Если обработка завершена, возвращаем результат в нужном формате
    if status_data.get("status") == "completed" and "result" in status_data:
        result = status_data["result"]
        return {
            "status": "completed",
            "video_id": video_id,
            "transcript": result.get("transcript", {"segments": []}),
            "highlights": result.get("highlights", [])
        }
    
    # Иначе возвращаем текущий статус
    return status_data

@app.get("/api/videos/{video_id}/transcript")
async def get_video_transcript(video_id: str):
    """Получение транскрипта видео"""
    # Проверяем статус задачи
    if video_id in task_status:
        status_data = task_status[video_id]
        if status_data.get("status") == "completed" and "result" in status_data:
            result = status_data["result"]
            return result.get("transcript", {"segments": []})
    
    # Проверяем наличие сохраненного транскрипта
    transcript_path = os.path.join(RESULTS_DIR, f"{video_id}_transcript.json")
    if os.path.exists(transcript_path):
        with open(transcript_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    raise HTTPException(status_code=404, detail="Transcript not found")

@app.get("/api/videos/{video_id}/highlights")
async def get_video_highlights(video_id: str):
    """Получение выделенных моментов видео"""
    # Проверяем статус задачи
    if video_id in task_status:
        status_data = task_status[video_id]
        if status_data.get("status") == "completed" and "result" in status_data:
            result = status_data["result"]
            return {"highlights": result.get("highlights", [])}
    
    # Проверяем наличие сохраненного анализа
    analysis_path = os.path.join(RESULTS_DIR, f"{video_id}_analysis.json")
    if os.path.exists(analysis_path):
        with open(analysis_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    raise HTTPException(status_code=404, detail="Highlights not found")

@app.get("/api/videos/{video_id}/download")
async def download_video(video_id: str):
    """Скачивание исходного видео"""
    video_path = os.path.join(UPLOAD_DIR, f"{video_id}.mp4")
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")
    
    return FileResponse(
        path=video_path,
        filename=f"{video_id}.mp4",
        media_type="video/mp4"
    )

@app.get("/health")
async def health_check():
    """Проверка работоспособности API"""
    return {
        "status": "ok",
        "version": "21.0.0",
        "timestamp": datetime.now().isoformat(),
        "whisper_model": "tiny" if whisper_model is not None else None,
        "supabase_available": supabase_available,
        "queue_size": len(task_status),
        "processing_tasks": sum(1 for status in task_status.values() 
                               if status.get("status") == "processing"),
        "queued_tasks": sum(1 for status in task_status.values() 
                           if status.get("status") == "queued")
    }

# ASS субтитры endpoints
@app.get("/api/videos/{video_id}/subtitles/ass")
async def get_video_ass_subtitles(video_id: str):
    """Получение ASS субтитров для видео"""
    # Проверяем статус задачи
    if video_id not in task_status or task_status[video_id].get("status") != "completed":
        raise HTTPException(status_code=404, detail="Video processing not completed")
    
    try:
        # Получаем транскрипт
        transcript_path = os.path.join(RESULTS_DIR, f"{video_id}_transcript.json")
        if not os.path.exists(transcript_path):
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        with open(transcript_path, 'r', encoding='utf-8') as f:
            transcript = json.load(f)
        
        # Генерируем ASS субтитры
        from ass_generator import ASSGenerator
        ass_generator = ASSGenerator()
        
        # Путь для сохранения
        ass_path = os.path.join(RESULTS_DIR, f"{video_id}.ass")
        
        # Генерируем и сохраняем
        ass_content = ass_generator.generate_from_whisper(transcript)
        with open(ass_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        
        return FileResponse(
            path=ass_path,
            filename=f"{video_id}.ass",
            media_type="text/plain"
        )
    except Exception as e:
        logger.error(f"❌ Ошибка генерации ASS субтитров: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Генерация клипов
@app.post("/api/clips/generate")
async def generate_clip(request: ClipGenerationRequest):
    """Генерация клипа из видео"""
    video_id = request.video_id
    format_id = request.format_id
    style_id = request.style_id
    
    try:
        logger.info(f"🔄 Генерация клипа для видео {video_id}, формат {format_id}, стиль {style_id}")
        
        # Проверяем существование видео
        video_path = os.path.join(UPLOAD_DIR, f"{video_id}.mp4")
        if not os.path.exists(video_path):
            logger.error(f"❌ Видео не найдено: {video_path}")
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Проверяем завершение обработки
        if video_id not in task_status:
            logger.error(f"❌ Видео {video_id} не найдено в статусах задач")
            raise HTTPException(status_code=400, detail="Video not found in task status")
        
        if task_status[video_id].get("status") != "completed":
            current_status = task_status[video_id].get("status", "unknown")
            logger.error(f"❌ Видео {video_id} не завершено. Текущий статус: {current_status}")
            raise HTTPException(status_code=400, detail=f"Video processing not completed. Status: {current_status}")
        
        logger.info(f"✅ Видео {video_id} успешно обработано, получаем highlights")
        
        # Получаем выделенные моменты из статуса задачи
        task_result = task_status[video_id].get("result", {})
        highlights = task_result.get("highlights", [])
        
        logger.info(f"📊 Найдено {len(highlights)} highlights в статусе задачи")
        
        # Если нет в статусе, пробуем загрузить из файла
        if not highlights:
            logger.info("🔍 Highlights не найдены в статусе, ищем в файле...")
            analysis_path = os.path.join(RESULTS_DIR, f"{video_id}_analysis.json")
            if os.path.exists(analysis_path):
                with open(analysis_path, 'r', encoding='utf-8') as f:
                    analysis = json.load(f)
                highlights = analysis.get("highlights", [])
                logger.info(f"📊 Найдено {len(highlights)} highlights в файле")
            else:
                logger.warning(f"⚠️ Файл анализа не найден: {analysis_path}")
        if not highlights:
            raise HTTPException(status_code=404, detail="No highlights found")
        
        # Генерируем клип для выбранного highlight
        highlight_index = request.highlight_index
        if highlight_index >= len(highlights):
            logger.warning(f"⚠️ Запрошенный индекс {highlight_index} больше количества highlights {len(highlights)}, используем последний")
            highlight_index = len(highlights) - 1
        
        highlight = highlights[highlight_index]
        
        # Проверяем что highlight это словарь, а не строка
        if isinstance(highlight, str):
            logger.error(f"❌ Highlight является строкой, а не объектом: {highlight}")
            raise HTTPException(status_code=500, detail="Invalid highlight format")
        
        if not isinstance(highlight, dict):
            logger.error(f"❌ Highlight не является словарем: {type(highlight)}")
            raise HTTPException(status_code=500, detail="Invalid highlight format")
        
        # Проверяем наличие обязательных полей
        if "start_time" not in highlight or "end_time" not in highlight:
            logger.error(f"❌ Highlight не содержит start_time или end_time: {highlight}")
            raise HTTPException(status_code=500, detail="Missing time fields in highlight")
        
        start_time = highlight["start_time"]
        end_time = highlight["end_time"]
        
        # Проверяем что времена являются числами
        if not isinstance(start_time, (int, float)) or not isinstance(end_time, (int, float)):
            logger.error(f"❌ Некорректные времена в highlight: start={start_time}, end={end_time}")
            raise HTTPException(status_code=500, detail="Invalid time values in highlight")
        
        logger.info(f"🎬 Генерируем клип #{highlight_index + 1} из {len(highlights)}: {start_time}s - {end_time}s")
        
        # Генерируем уникальный ID для клипа
        clip_id = str(uuid.uuid4())
        
        # Путь для сохранения
        clip_path = os.path.join(CLIPS_DIR, f"{clip_id}.mp4")
        
        # Получаем транскрипт для субтитров
        transcript_segments = task_result.get("transcript", [])
        
        # Фильтруем сегменты для данного временного отрезка
        clip_segments = []
        for segment in transcript_segments:
            seg_start = segment.get("start", 0)
            seg_end = segment.get("end", 0)
            
            # Проверяем пересечение с клипом
            if seg_end > start_time and seg_start < end_time:
                # Корректируем время относительно начала клипа
                adjusted_segment = {
                    "start": max(0, seg_start - start_time),
                    "end": min(end_time - start_time, seg_end - start_time),
                    "text": segment.get("text", "")
                }
                clip_segments.append(adjusted_segment)
        
        logger.info(f"📝 Найдено {len(clip_segments)} сегментов субтитров для клипа")
        
        # Создаем субтитры с караоке-эффектами
        subtitle_filter = ""
        if clip_segments:
            subtitle_filter = create_subtitle_filter(clip_segments, style_id)
            logger.info(f"✨ Создан фильтр субтитров: {len(subtitle_filter)} символов")
        
        # Создаем фильтр обрезки для формата 9:16
        crop_filter = ""
        if format_id == "9:16":
            crop_filter = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        elif format_id == "16:9":
            crop_filter = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
        elif format_id == "1:1":
            crop_filter = "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
        
        # Объединяем фильтры
        video_filter = ""
        if crop_filter and subtitle_filter:
            video_filter = f"{crop_filter},{subtitle_filter}"
        elif crop_filter:
            video_filter = crop_filter
        elif subtitle_filter:
            video_filter = subtitle_filter
        
        # Команда FFmpeg для вырезания клипа с субтитрами
        cmd = [
            'ffmpeg', '-i', video_path,
            '-ss', str(start_time),
            '-to', str(end_time),
            '-c:v', 'libx264', '-c:a', 'aac',
            '-strict', 'experimental',
            '-b:a', '128k'
        ]
        
        # Добавляем видео фильтр если есть
        if video_filter:
            cmd.extend(['-vf', video_filter])
        
        cmd.extend(['-y', clip_path])
        
        logger.info(f"🎬 Команда FFmpeg: {' '.join(cmd[:10])}...")
        
        # Запускаем FFmpeg
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if not os.path.exists(clip_path):
            logger.error(f"❌ Ошибка генерации клипа: {result.stderr}")
            raise HTTPException(status_code=500, detail="Clip generation failed")
        
        # Загружаем в Supabase если доступен
        clip_url = upload_clip_to_supabase(clip_path, f"{clip_id}.mp4")
        
        # Возвращаем информацию о клипе
        result = {
            "clip_id": clip_id,
            "video_id": video_id,
            "format_id": format_id,
            "style_id": style_id,
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "title": highlight.get("title", "Клип"),
            "description": highlight.get("description", ""),
            "url": clip_url
        }
        
        # Сохраняем как последний сгенерированный клип
        global last_generated_clip
        last_generated_clip = result.copy()
        
        logger.info(f"✅ Клип успешно сгенерирован: {clip_id}")
        logger.info(f"📊 Возвращаемый результат: {result}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка генерации клипа: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/clips/generate-all")
async def generate_all_clips(request: ClipGenerationRequest):
    """Генерация всех клипов из видео"""
    video_id = request.video_id
    format_id = request.format_id
    style_id = request.style_id
    
    try:
        logger.info(f"🔄 Генерация всех клипов для видео {video_id}, формат {format_id}, стиль {style_id}")
        
        # Проверяем существование видео
        video_path = os.path.join(UPLOAD_DIR, f"{video_id}.mp4")
        if not os.path.exists(video_path):
            logger.error(f"❌ Видео не найдено: {video_path}")
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Проверяем завершение обработки
        if video_id not in task_status:
            logger.error(f"❌ Видео {video_id} не найдено в статусах задач")
            raise HTTPException(status_code=400, detail="Video not found in task status")
        
        if task_status[video_id].get("status") != "completed":
            current_status = task_status[video_id].get("status", "unknown")
            logger.error(f"❌ Видео {video_id} не завершено. Текущий статус: {current_status}")
            raise HTTPException(status_code=400, detail=f"Video processing not completed. Status: {current_status}")
        
        # Получаем выделенные моменты
        task_result = task_status[video_id].get("result", {})
        highlights = task_result.get("highlights", [])
        
        if not highlights:
            # Пробуем загрузить из файла
            analysis_path = os.path.join(RESULTS_DIR, f"{video_id}_analysis.json")
            if os.path.exists(analysis_path):
                with open(analysis_path, 'r', encoding='utf-8') as f:
                    analysis = json.load(f)
                highlights = analysis.get("highlights", [])
        
        if not highlights:
            raise HTTPException(status_code=404, detail="No highlights found")
        
        logger.info(f"📊 Найдено {len(highlights)} highlights для генерации")
        
        # Генерируем все клипы
        generated_clips = []
        transcript_segments = task_result.get("transcript", [])
        
        for i, highlight in enumerate(highlights):
            try:
                # Проверяем что highlight это словарь, а не строка
                if isinstance(highlight, str):
                    logger.error(f"❌ Highlight #{i + 1} является строкой, а не объектом: {highlight}")
                    continue
                
                if not isinstance(highlight, dict):
                    logger.error(f"❌ Highlight #{i + 1} не является словарем: {type(highlight)}")
                    continue
                
                # Проверяем наличие обязательных полей
                if "start_time" not in highlight or "end_time" not in highlight:
                    logger.error(f"❌ Highlight #{i + 1} не содержит start_time или end_time: {highlight}")
                    continue
                
                start_time = highlight["start_time"]
                end_time = highlight["end_time"]
                
                # Проверяем что времена являются числами
                if not isinstance(start_time, (int, float)) or not isinstance(end_time, (int, float)):
                    logger.error(f"❌ Некорректные времена в highlight #{i + 1}: start={start_time}, end={end_time}")
                    continue
                
                # Генерируем уникальный ID для клипа
                clip_id = str(uuid.uuid4())
                clip_path = os.path.join(CLIPS_DIR, f"{clip_id}.mp4")
                
                logger.info(f"🎬 Генерируем клип #{i + 1}/{len(highlights)}: {start_time}s - {end_time}s")
                
                # Фильтруем сегменты для данного временного отрезка
                clip_segments = []
                for segment in transcript_segments:
                    seg_start = segment.get("start", 0)
                    seg_end = segment.get("end", 0)
                    
                    if seg_end > start_time and seg_start < end_time:
                        adjusted_segment = {
                            "start": max(0, seg_start - start_time),
                            "end": min(end_time - start_time, seg_end - start_time),
                            "text": segment.get("text", "")
                        }
                        clip_segments.append(adjusted_segment)
                
                # Создаем субтитры
                subtitle_filter = ""
                if clip_segments:
                    subtitle_filter = create_subtitle_filter(clip_segments, style_id)
                
                # Создаем фильтр обрезки
                crop_filter = ""
                if format_id == "9:16":
                    crop_filter = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
                elif format_id == "16:9":
                    crop_filter = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
                elif format_id == "1:1":
                    crop_filter = "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
                
                # Объединяем фильтры
                video_filter = ""
                if crop_filter and subtitle_filter:
                    video_filter = f"{crop_filter},{subtitle_filter}"
                elif crop_filter:
                    video_filter = crop_filter
                elif subtitle_filter:
                    video_filter = subtitle_filter
                
                # Команда FFmpeg
                cmd = [
                    'ffmpeg', '-i', video_path,
                    '-ss', str(start_time),
                    '-to', str(end_time),
                    '-c:v', 'libx264', '-c:a', 'aac',
                    '-strict', 'experimental',
                    '-b:a', '128k'
                ]
                
                if video_filter:
                    cmd.extend(['-vf', video_filter])
                
                cmd.extend(['-y', clip_path])
                
                # Запускаем FFmpeg
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if os.path.exists(clip_path):
                    # Загружаем в Supabase
                    clip_url = upload_clip_to_supabase(clip_path, f"{clip_id}.mp4")
                    
                    clip_info = {
                        "clip_id": clip_id,
                        "highlight_index": i,
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration": end_time - start_time,
                        "title": highlight.get("title", f"Клип {i + 1}"),
                        "description": highlight.get("description", ""),
                        "url": clip_url
                    }
                    
                    generated_clips.append(clip_info)
                    logger.info(f"✅ Клип #{i + 1} сгенерирован: {clip_id}")
                else:
                    logger.error(f"❌ Ошибка генерации клипа #{i + 1}: {result.stderr}")
                    
            except Exception as e:
                logger.error(f"❌ Ошибка генерации клипа #{i + 1}: {e}")
                continue
        
        if not generated_clips:
            raise HTTPException(status_code=500, detail="Failed to generate any clips")
        
        logger.info(f"✅ Успешно сгенерировано {len(generated_clips)} из {len(highlights)} клипов")
        
        return {
            "video_id": video_id,
            "format_id": format_id,
            "style_id": style_id,
            "total_highlights": len(highlights),
            "generated_clips": len(generated_clips),
            "clips": generated_clips
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка генерации всех клипов: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/clips/download/{clip_id}")
async def download_clip(clip_id: str):
    """Скачивание клипа"""
    clip_path = os.path.join(CLIPS_DIR, f"{clip_id}.mp4")
    if not os.path.exists(clip_path):
        raise HTTPException(status_code=404, detail="Clip not found")
    
    return FileResponse(
        path=clip_path,
        filename=f"{clip_id}.mp4",
        media_type="video/mp4"
    )

def create_subtitle_filter(segments, style='modern'):
    """Создает FFmpeg фильтр для субтитров с караоке-эффектами"""
    if not segments:
        return ""
    
    # Стили субтитров
    styles = {
        'modern': {
            'fontsize': 48,
            'fontcolor': 'white',
            'bordercolor': 'black',
            'borderw': 3,
            'shadowcolor': 'black@0.5',
            'shadowx': 2,
            'shadowy': 2
        },
        'neon': {
            'fontsize': 52,
            'fontcolor': 'cyan',
            'bordercolor': 'magenta',
            'borderw': 2,
            'shadowcolor': 'black@0.8',
            'shadowx': 3,
            'shadowy': 3
        },
        'fire': {
            'fontsize': 50,
            'fontcolor': 'orange',
            'bordercolor': 'red',
            'borderw': 3,
            'shadowcolor': 'black@0.6',
            'shadowx': 2,
            'shadowy': 2
        },
        'elegant': {
            'fontsize': 46,
            'fontcolor': 'gold',
            'bordercolor': 'black',
            'borderw': 2,
            'shadowcolor': 'black@0.4',
            'shadowx': 1,
            'shadowy': 1
        }
    }
    
    current_style = styles.get(style, styles['modern'])
    
    # Объединяем пересекающиеся сегменты чтобы избежать наложений
    merged_segments = []
    for segment in sorted(segments, key=lambda x: x['start']):
        text = segment['text'].strip()
        if not text:
            continue
            
        start_time = segment['start']
        end_time = segment['end']
        
        # Проверяем пересечение с последним сегментом
        if merged_segments and start_time < merged_segments[-1]['end']:
            # Объединяем с предыдущим сегментом
            merged_segments[-1]['text'] += ' ' + text
            merged_segments[-1]['end'] = max(merged_segments[-1]['end'], end_time)
        else:
            # Добавляем новый сегмент
            merged_segments.append({
                'start': start_time,
                'end': end_time,
                'text': text
            })
    
    # Создаем drawtext фильтры для каждого объединенного сегмента
    drawtext_filters = []
    
    for i, segment in enumerate(merged_segments):
        start_time = segment['start']
        end_time = segment['end']
        text = segment['text'].strip()
        
        if not text:
            continue
        
        # Экранируем специальные символы для FFmpeg
        text = text.replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")
        
        # Ограничиваем длину текста для лучшего отображения
        if len(text) > 80:
            text = text[:77] + "..."
        
        # Создаем drawtext фильтр с караоке-эффектом
        drawtext = f"drawtext=text='{text}':fontsize={current_style['fontsize']}:fontcolor={current_style['fontcolor']}:bordercolor={current_style['bordercolor']}:borderw={current_style['borderw']}:shadowcolor={current_style['shadowcolor']}:shadowx={current_style['shadowx']}:shadowy={current_style['shadowy']}:x=(w-text_w)/2:y=h-text_h-50:enable='between(t,{start_time},{end_time})'"
        
        drawtext_filters.append(drawtext)
    
    if not drawtext_filters:
        return ""
    
    # Объединяем все фильтры
    return ",".join(drawtext_filters)

# Глобальная переменная для хранения последнего сгенерированного клипа
last_generated_clip = None

@app.get("/api/clips/generation/{clip_id}/status")
async def get_clip_generation_status(clip_id: str):
    """Получение статуса генерации клипа"""
    global last_generated_clip
    
    try:
        # Если clip_id = "undefined", возвращаем последний сгенерированный клип
        if clip_id == "undefined" and last_generated_clip:
            logger.info(f"🔄 Запрос статуса для undefined, возвращаем последний клип: {last_generated_clip['clip_id']}")
            return {
                "status": "completed",
                "clip_id": last_generated_clip["clip_id"],
                "message": "Клип успешно сгенерирован",
                "download_url": last_generated_clip["url"],
                "title": last_generated_clip.get("title", "Клип"),
                "description": last_generated_clip.get("description", "")
            }
        
        # Проверяем существование клипа
        clip_path = os.path.join(CLIPS_DIR, f"{clip_id}.mp4")
        
        if os.path.exists(clip_path):
            # Клип готов
            return {
                "status": "completed",
                "clip_id": clip_id,
                "message": "Клип успешно сгенерирован",
                "download_url": f"/api/clips/download/{clip_id}"
            }
        else:
            # Клип не найден
            return {
                "status": "not_found",
                "clip_id": clip_id,
                "message": "Клип не найден"
            }
            
    except Exception as e:
        logger.error(f"❌ Ошибка проверки статуса клипа {clip_id}: {e}")
        return {
            "status": "error",
            "clip_id": clip_id,
            "message": f"Ошибка: {str(e)}"
        }

# Запуск приложения
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)

