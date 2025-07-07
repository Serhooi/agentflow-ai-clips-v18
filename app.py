# AgentFlow AI Clips v19.0.0 - ShortGPT Integration
# Полная интеграция с ShortGPT + караоке-эффекты

import os
import sys
import json
import logging
import tempfile
import subprocess
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

# FastAPI
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

# ShortGPT imports
sys.path.append('/home/ubuntu/ShortGPT')
from shortGPT.engine.content_short_engine import ContentShortEngine
from shortGPT.audio.voice_module import VoiceModule
from shortGPT.config.languages import Language
from shortGPT.editing_utils.captions import getCaptionsWithTime
from shortGPT.audio import audio_utils

# Whisper для транскрибации
import whisper_timestamped as whisper

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('agentflow_shortgpt.log')
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация
class Config:
    UPLOAD_DIR = "/tmp/agentflow_uploads"
    CLIPS_DIR = "/tmp/agentflow_clips"
    TEMP_DIR = "/tmp/agentflow_temp"
    
    # OpenAI API
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    # Supabase (опционально)
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Создаем директории
for directory in [Config.UPLOAD_DIR, Config.CLIPS_DIR, Config.TEMP_DIR]:
    os.makedirs(directory, exist_ok=True)

# FastAPI приложение
app = FastAPI(title="AgentFlow AI Clips", version="19.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic модели
class VideoAnalysisRequest(BaseModel):
    video_id: str

class ClipGenerationRequest(BaseModel):
    video_id: str
    format_id: str = "9:16"
    style_id: str = "modern"
    num_clips: int = 3

class VideoStatus(BaseModel):
    status: str
    progress: float
    highlights: List[Dict] = []
    error: Optional[str] = None

# Глобальные переменные для хранения состояния
video_status = {}
video_data = {}

# Караоке-система ASS (из нашей предыдущей версии)
class KaraokeSubtitleSystem:
    """Система создания караоке-субтитров в формате ASS"""
    
    def __init__(self):
        self.styles = {
            "modern": {
                "primary_colour": "&H00FFFFFF",  # Белый
                "secondary_colour": "&H0000FF00",  # Зеленый для караоке
                "outline_colour": "&H00000000",   # Черная обводка
                "back_colour": "&H80000000",      # Полупрозрачный фон
                "font_name": "Arial",
                "font_size": 24,
                "bold": True
            },
            "neon": {
                "primary_colour": "&H00FFFF00",  # Циан
                "secondary_colour": "&H00FF00FF",  # Магента для караоке
                "outline_colour": "&H00000000",
                "back_colour": "&H80000000",
                "font_name": "Arial",
                "font_size": 26,
                "bold": True
            },
            "fire": {
                "primary_colour": "&H0000FFFF",  # Желтый
                "secondary_colour": "&H000080FF",  # Оранжевый для караоке
                "outline_colour": "&H00000000",
                "back_colour": "&H80000000",
                "font_name": "Arial",
                "font_size": 25,
                "bold": True
            },
            "elegant": {
                "primary_colour": "&H00FFFFFF",  # Белый
                "secondary_colour": "&H0000FFFF",  # Желтый для караоке
                "outline_colour": "&H00000000",
                "back_colour": "&H80000000",
                "font_name": "Times New Roman",
                "font_size": 24,
                "bold": False
            }
        }
    
    def create_ass_file(self, words_data: List[Dict], style: str = "modern", duration: float = 30.0) -> str:
        """Создает ASS файл с караоке-эффектами"""
        
        style_config = self.styles.get(style, self.styles["modern"])
        
        # Заголовок ASS файла
        ass_content = f"""[Script Info]
Title: AgentFlow Karaoke Subtitles
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style_config['font_name']},{style_config['font_size']},{style_config['primary_colour']},{style_config['secondary_colour']},{style_config['outline_colour']},{style_config['back_colour']},{1 if style_config['bold'] else 0},0,0,0,100,100,0,0,1,2,0,2,10,10,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        # Группируем слова в фразы (максимум 3 слова, максимум 2.5 секунды)
        phrases = self._group_words_into_phrases(words_data, max_words=3, max_duration=2.5)
        
        # Создаем события для каждой фразы
        for phrase in phrases:
            start_time = self._format_ass_time(phrase['start'])
            end_time = self._format_ass_time(phrase['end'])
            
            # Создаем караоке-эффект для каждого слова в фразе
            karaoke_text = self._create_karaoke_text(phrase['words'])
            
            ass_content += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{karaoke_text}\\N\n"
        
        # Сохраняем в временный файл
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.ass', delete=False, encoding='utf-8')
        temp_file.write(ass_content)
        temp_file.close()
        
        logger.info(f"📝 ASS файл создан: {temp_file.name}")
        return temp_file.name
    
    def _group_words_into_phrases(self, words_data: List[Dict], max_words: int = 3, max_duration: float = 2.5) -> List[Dict]:
        """Группирует слова в фразы с ограничениями"""
        phrases = []
        current_phrase = []
        phrase_start = None
        
        for word_data in words_data:
            if not current_phrase:
                phrase_start = word_data['start']
                current_phrase = [word_data]
            else:
                # Проверяем ограничения
                phrase_duration = word_data['end'] - phrase_start
                
                if len(current_phrase) >= max_words or phrase_duration > max_duration:
                    # Завершаем текущую фразу
                    phrases.append({
                        'start': phrase_start,
                        'end': current_phrase[-1]['end'],
                        'words': current_phrase.copy()
                    })
                    
                    # Начинаем новую фразу
                    phrase_start = word_data['start']
                    current_phrase = [word_data]
                else:
                    current_phrase.append(word_data)
        
        # Добавляем последнюю фразу
        if current_phrase:
            phrases.append({
                'start': phrase_start,
                'end': current_phrase[-1]['end'],
                'words': current_phrase.copy()
            })
        
        return phrases
    
    def _create_karaoke_text(self, words: List[Dict]) -> str:
        """Создает караоке-текст для фразы"""
        karaoke_parts = []
        
        for i, word_data in enumerate(words):
            word = word_data['word'].strip()
            
            # Вычисляем длительность слова в сантисекундах (1/100 секунды)
            duration = max(20, min(150, int((word_data['end'] - word_data['start']) * 100)))
            
            # Добавляем караоке-эффект
            karaoke_parts.append(f"{{\\kf{duration}}}{word}")
        
        return "".join(karaoke_parts)
    
    def _format_ass_time(self, seconds: float) -> str:
        """Форматирует время в формат ASS (H:MM:SS.CC)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centiseconds = int((seconds % 1) * 100)
        
        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

# Инициализируем караоке-систему
karaoke_system = KaraokeSubtitleSystem()

# Whisper модель
whisper_model = None

def load_whisper_model():
    """Загружает модель Whisper"""
    global whisper_model
    if whisper_model is None:
        logger.info("🎤 Загружаем модель Whisper...")
        whisper_model = whisper.load_model("base")
        logger.info("✅ Модель Whisper загружена")
    return whisper_model

# API Endpoints

@app.get("/")
async def root():
    """Главная страница API"""
    return {"message": "AgentFlow AI Clips API v19.0.0 (ShortGPT)", "status": "running"}

@app.get("/health")
async def health_check():
    """Проверка состояния сервиса"""
    return {
        "status": "healthy",
        "version": "19.0.0",
        "timestamp": datetime.now().isoformat(),
        "shortgpt_integration": True,
        "karaoke_subtitles": True
    }

@app.post("/api/videos/upload")
async def upload_video(file: UploadFile = File(...)):
    """Загрузка видео файла"""
    try:
        # Генерируем уникальный ID
        video_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        
        # Сохраняем файл
        file_path = os.path.join(Config.UPLOAD_DIR, f"{video_id}.mp4")
        
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Получаем информацию о видео
        file_size = len(content)
        
        # Инициализируем статус
        video_status[video_id] = {
            "status": "uploaded",
            "progress": 0.0,
            "highlights": [],
            "error": None
        }
        
        video_data[video_id] = {
            "file_path": file_path,
            "file_size": file_size,
            "upload_time": datetime.now().isoformat()
        }
        
        logger.info(f"✅ Видео загружено: {video_id}, размер: {file_size} байт")
        
        return {
            "video_id": video_id,
            "status": "uploaded",
            "file_size": file_size
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки видео: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/videos/analyze")
async def analyze_video(request: VideoAnalysisRequest, background_tasks: BackgroundTasks):
    """Анализ видео для поиска лучших моментов"""
    try:
        video_id = request.video_id
        
        if video_id not in video_data:
            raise HTTPException(status_code=404, detail="Видео не найдено")
        
        # Запускаем анализ в фоне
        background_tasks.add_task(perform_video_analysis, video_id)
        
        # Обновляем статус
        video_status[video_id]["status"] = "analyzing"
        video_status[video_id]["progress"] = 0.1
        
        logger.info(f"🔍 Начат анализ видео: {video_id}")
        
        return {"message": "Анализ начат", "video_id": video_id}
        
    except Exception as e:
        logger.error(f"❌ Ошибка анализа видео: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def perform_video_analysis(video_id: str):
    """Выполняет анализ видео в фоновом режиме"""
    try:
        file_path = video_data[video_id]["file_path"]
        
        # Обновляем прогресс
        video_status[video_id]["progress"] = 0.2
        
        # Загружаем Whisper
        model = load_whisper_model()
        
        # Обновляем прогресс
        video_status[video_id]["progress"] = 0.4
        
        # Транскрибируем аудио
        logger.info(f"🎤 Начинаем транскрибацию: {video_id}")
        result = whisper.transcribe(model, file_path, language="en")
        
        # Обновляем прогресс
        video_status[video_id]["progress"] = 0.7
        
        # Анализируем транскрипцию для поиска лучших моментов
        highlights = analyze_transcript_for_highlights(result, video_id)
        
        # Сохраняем результаты
        video_data[video_id]["transcription"] = result
        video_data[video_id]["highlights"] = highlights
        
        # Обновляем статус
        video_status[video_id]["status"] = "completed"
        video_status[video_id]["progress"] = 1.0
        video_status[video_id]["highlights"] = highlights
        
        logger.info(f"✅ Анализ завершен: {video_id}, найдено {len(highlights)} highlights")
        
    except Exception as e:
        logger.error(f"❌ Ошибка анализа видео {video_id}: {e}")
        video_status[video_id]["status"] = "error"
        video_status[video_id]["error"] = str(e)

def analyze_transcript_for_highlights(transcription: Dict, video_id: str) -> List[Dict]:
    """Анализирует транскрипцию для поиска лучших моментов"""
    
    # Получаем общую длительность
    total_duration = transcription.get('segments', [])[-1]['end'] if transcription.get('segments') else 30
    
    # Создаем 3-5 клипов в зависимости от длительности
    if total_duration < 30:
        num_clips = 2
    elif total_duration < 60:
        num_clips = 3
    elif total_duration < 120:
        num_clips = 4
    else:
        num_clips = 5
    
    clip_duration = min(20, total_duration / num_clips)
    
    highlights = []
    
    for i in range(num_clips):
        start_time = i * (total_duration / num_clips)
        end_time = min(start_time + clip_duration, total_duration)
        
        # Находим соответствующие сегменты
        relevant_segments = []
        for segment in transcription.get('segments', []):
            if segment['start'] >= start_time and segment['end'] <= end_time:
                relevant_segments.append(segment)
        
        if relevant_segments:
            highlight_text = " ".join([seg['text'] for seg in relevant_segments])
            
            highlights.append({
                "id": f"{video_id}_highlight_{i+1}",
                "start": start_time,
                "end": end_time,
                "text": highlight_text.strip(),
                "score": 0.8 + (i * 0.05),  # Простая оценка
                "segments": relevant_segments
            })
    
    return highlights

@app.get("/api/videos/{video_id}/status")
async def get_video_status(video_id: str):
    """Получение статуса анализа видео"""
    if video_id not in video_status:
        raise HTTPException(status_code=404, detail="Видео не найдено")
    
    return video_status[video_id]

@app.post("/api/clips/generate")
async def generate_clips(request: ClipGenerationRequest, background_tasks: BackgroundTasks):
    """Генерация клипов из видео"""
    try:
        video_id = request.video_id
        
        if video_id not in video_data:
            raise HTTPException(status_code=404, detail="Видео не найдено")
        
        if video_status[video_id]["status"] != "completed":
            raise HTTPException(status_code=400, detail="Анализ видео не завершен")
        
        # Генерируем ID задачи
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{video_id}"
        
        # Запускаем генерацию в фоне
        background_tasks.add_task(
            perform_clip_generation, 
            task_id, 
            video_id, 
            request.format_id, 
            request.style_id,
            request.num_clips
        )
        
        logger.info(f"🎬 Начата генерация клипов: {task_id}")
        
        return {"task_id": task_id, "message": "Генерация начата"}
        
    except Exception as e:
        logger.error(f"❌ Ошибка генерации клипов: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Глобальное хранилище статусов задач
task_status = {}

async def perform_clip_generation(task_id: str, video_id: str, format_id: str, style_id: str, num_clips: int):
    """Выполняет генерацию клипов в фоновом режиме"""
    try:
        # Инициализируем статус задачи
        task_status[task_id] = {
            "status": "processing",
            "progress": 0.0,
            "clips": [],
            "error": None
        }
        
        file_path = video_data[video_id]["file_path"]
        highlights = video_data[video_id]["highlights"]
        transcription = video_data[video_id]["transcription"]
        
        # Ограничиваем количество клипов
        clips_to_generate = highlights[:num_clips]
        
        generated_clips = []
        
        for i, highlight in enumerate(clips_to_generate):
            try:
                logger.info(f"🎬 Создаем клип {i+1}/{len(clips_to_generate)}")
                
                # Обновляем прогресс
                progress = (i / len(clips_to_generate)) * 0.9
                task_status[task_id]["progress"] = progress
                
                # Создаем клип с караоке-субтитрами
                clip_path = await create_clip_with_karaoke_subtitles(
                    file_path,
                    highlight,
                    transcription,
                    format_id,
                    style_id,
                    task_id,
                    i + 1
                )
                
                if clip_path:
                    clip_info = {
                        "id": f"{task_id}_clip_{i+1}",
                        "path": clip_path,
                        "start": highlight["start"],
                        "end": highlight["end"],
                        "text": highlight["text"],
                        "format": format_id,
                        "style": style_id
                    }
                    generated_clips.append(clip_info)
                    logger.info(f"✅ Клип {i+1} создан: {clip_path}")
                else:
                    logger.error(f"❌ Не удалось создать клип {i+1}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка создания клипа {i+1}: {e}")
                continue
        
        # Завершаем задачу
        task_status[task_id]["status"] = "completed"
        task_status[task_id]["progress"] = 1.0
        task_status[task_id]["clips"] = generated_clips
        
        logger.info(f"🎉 Генерация завершена: {task_id}, создано {len(generated_clips)} клипов")
        
    except Exception as e:
        logger.error(f"❌ Ошибка генерации клипов {task_id}: {e}")
        task_status[task_id]["status"] = "error"
        task_status[task_id]["error"] = str(e)

async def create_clip_with_karaoke_subtitles(
    video_path: str,
    highlight: Dict,
    transcription: Dict,
    format_id: str,
    style_id: str,
    task_id: str,
    clip_number: int
) -> Optional[str]:
    """Создает клип с караоке-субтитрами"""
    try:
        # Нормализуем format_id
        format_id = format_id.replace('_', ':')
        
        # Определяем выходной путь
        output_filename = f"{task_id}_clip_{clip_number}_{format_id.replace(':', 'x')}.mp4"
        output_path = os.path.join(Config.CLIPS_DIR, output_filename)
        
        # Извлекаем слова для данного временного отрезка
        clip_words = extract_words_for_timeframe(
            transcription,
            highlight["start"],
            highlight["end"]
        )
        
        if not clip_words:
            logger.warning(f"⚠️ Нет слов для клипа {clip_number}")
            return None
        
        # Создаем ASS файл с караоке-эффектами
        ass_file = karaoke_system.create_ass_file(clip_words, style_id)
        
        # Определяем параметры кадрирования
        crop_params = get_crop_parameters(format_id)
        
        # Создаем клип с субтитрами
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-ss', str(highlight["start"]),
            '-t', str(highlight["end"] - highlight["start"]),
            '-vf', f'{crop_params},ass={ass_file}',
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-avoid_negative_ts', 'make_zero',
            '-y', output_path
        ]
        
        logger.info(f"🎬 Выполняем FFmpeg команду для клипа {clip_number}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        # Удаляем временный ASS файл
        if os.path.exists(ass_file):
            os.remove(ass_file)
        
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
        else:
            logger.error(f"❌ FFmpeg ошибка для клипа {clip_number}: {result.stderr}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Ошибка создания клипа {clip_number}: {e}")
        return None

def extract_words_for_timeframe(transcription: Dict, start_time: float, end_time: float) -> List[Dict]:
    """Извлекает слова для заданного временного отрезка"""
    words = []
    
    for segment in transcription.get('segments', []):
        if 'words' in segment:
            for word_data in segment['words']:
                word_start = word_data.get('start', 0)
                word_end = word_data.get('end', 0)
                
                # Проверяем пересечение с временным отрезком
                if (word_start >= start_time and word_start < end_time) or \
                   (word_end > start_time and word_end <= end_time) or \
                   (word_start < start_time and word_end > end_time):
                    
                    # Корректируем время относительно начала клипа
                    adjusted_start = max(0, word_start - start_time)
                    adjusted_end = min(end_time - start_time, word_end - start_time)
                    
                    if adjusted_end > adjusted_start:
                        words.append({
                            'word': word_data.get('text', '').strip(),
                            'start': adjusted_start,
                            'end': adjusted_end
                        })
    
    return words

def get_crop_parameters(format_id: str) -> str:
    """Возвращает параметры кадрирования для FFmpeg"""
    
    format_configs = {
        "9:16": "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280",
        "16:9": "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",
        "1:1": "scale=720:720:force_original_aspect_ratio=increase,crop=720:720",
        "4:5": "scale=720:900:force_original_aspect_ratio=increase,crop=720:900"
    }
    
    return format_configs.get(format_id, format_configs["9:16"])

@app.get("/api/clips/generation/{task_id}/status")
async def get_generation_status(task_id: str):
    """Получение статуса генерации клипов"""
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    return task_status[task_id]

@app.get("/api/clips/{clip_id}/download")
async def download_clip(clip_id: str):
    """Скачивание готового клипа"""
    # Ищем клип во всех задачах
    for task_id, task_data in task_status.items():
        if task_data.get("clips"):
            for clip in task_data["clips"]:
                if clip["id"] == clip_id:
                    clip_path = clip["path"]
                    if os.path.exists(clip_path):
                        return FileResponse(
                            clip_path,
                            media_type="video/mp4",
                            filename=os.path.basename(clip_path)
                        )
    
    raise HTTPException(status_code=404, detail="Клип не найден")

# Запуск приложения
if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 AgentFlow AI Clips v19.0.0 (ShortGPT) started!")
    logger.info("🎬 ShortGPT интеграция активирована")
    logger.info("🎤 Whisper транскрибация")
    logger.info("📝 Караоке-субтитры ASS")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)

