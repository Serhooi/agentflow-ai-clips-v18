# AgentFlow AI Clips v18.5.4 - Интеграция анимированных субтитров с клиентской подсветкой
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
    description="Система генерации клипов с анимированными субтитрами на клиенте",
    version="18.5.4"
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
    MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
    MAX_TASK_AGE = 24 * 60 * 60  # 24 часа
    CLEANUP_INTERVAL = 3600  # Очистка каждый час

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
        "scale": f"{new_width}:{new_height}",
        "crop": f"{target['target_width']}:{target['target_height']}:{crop_x}:{crop_y}"
    }

def create_clip_without_subtitles(video_path: str, start_time: float, end_time: float, output_path: str, format_type: str = "9:16") -> bool:
    """Создание клипа без субтитров"""
    try:
        logger.info(f"🎬 Начинаем создание клипа")
        logger.info(f"📊 Параметры: {start_time}-{end_time}s, формат {format_type}")

        crop_params = get_crop_parameters(1920, 1080, format_type)
        if not crop_params:
            logger.error(f"❌ Неподдерживаемый формат: {format_type}")
            return False

        temp_video_path = output_path.replace('.mp4', '_temp.mp4')
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

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

        os.rename(temp_video_path, output_path)
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка создания клипа: {e}")
        return False

# API Endpoints

@app.get("/")
async def root():
    """Главная страница API"""
    return {"message": "AgentFlow AI Clips API v18.5.4", "status": "running"}

@app.get("/health")
async def health_check():
    """Проверка состояния сервиса"""
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    upload_count = len([f for f in os.listdir(Config.UPLOAD_DIR) if os.path.isfile(os.path.join(Config.UPLOAD_DIR, f))])
    clip_count = len([f for f in os.listdir(Config.CLIPS_DIR) if os.path.isfile(os.path.join(Config.CLIPS_DIR, f))])
    return {
        "status": "healthy",
        "version": "18.5.4",
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
    """Анализ видео для выделения ключевых моментов и транскрипции"""
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
    """Получение статуса анализа видео с транскрипцией"""
    if video_id not in analysis_tasks:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    task = analysis_tasks[video_id]
    response = {
        "video_id": video_id,
        "status": task["status"],
        "filename": task.get("filename"),
        "duration": task.get("duration"),
        "upload_time": task.get("upload_time"),
        "transcript": task.get("transcript", {}).get("words", []) if task.get("status") == "completed" else []
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
    """Генерация клипов без субтитров (анимация на клиенте)"""
    try:
        video_id = request.video_id
        format_id = request.format_id
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
            "format_id": format_id
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
        analysis_task = analysis_tasks[video_id]
        video_path = analysis_task["video_path"]
        highlights = analysis_task["analysis"]["highlights"]
        generation_tasks[task_id]["status"] = "generating"
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
                clip_filename = f"{task_id}_clip_{i+1}_{format_id.replace(':', 'x')}.mp4"
                clip_path = os.path.join(Config.CLIPS_DIR, clip_filename)
                success = create_clip_without_subtitles(video_path, start_time, end_time, clip_path, format_id)
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
    """Скачивание клипа"""
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
    logger.info("🚀 AgentFlow AI Clips v18.5.4 started!")
    logger.info("🎬 Анимированные субтитры на клиенте активированы")
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
