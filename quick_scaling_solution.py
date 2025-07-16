# Быстрое решение для масштабирования текущего кода
# Добавляем Redis для очереди задач без полной переписки

import redis
import json
import uuid
from datetime import datetime
from typing import Dict, Optional
import asyncio
import logging

logger = logging.getLogger(__name__)

# Redis подключение
try:
    redis_client = redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True
    )
    REDIS_AVAILABLE = True
    logger.info("✅ Redis подключен")
except Exception as e:
    REDIS_AVAILABLE = False
    logger.warning(f"⚠️ Redis недоступен: {e}")

class TaskQueue:
    """Простая очередь задач на Redis"""
    
    def __init__(self):
        self.queue_name = "video_processing_queue"
        self.processing_set = "processing_tasks"
        self.results_prefix = "task_result:"
        
    def add_task(self, task_data: Dict) -> str:
        """Добавить задачу в очередь"""
        if not REDIS_AVAILABLE:
            return None
            
        task_id = str(uuid.uuid4())
        task_data["task_id"] = task_id
        task_data["created_at"] = datetime.now().isoformat()
        
        try:
            redis_client.lpush(self.queue_name, json.dumps(task_data))
            logger.info(f"📝 Задача добавлена в очередь: {task_id}")
            return task_id
        except Exception as e:
            logger.error(f"❌ Ошибка добавления задачи: {e}")
            return None
    
    def get_task(self) -> Optional[Dict]:
        """Получить задачу из очереди"""
        if not REDIS_AVAILABLE:
            return None
            
        try:
            # Блокирующее получение задачи (ждем до 5 секунд)
            result = redis_client.brpop(self.queue_name, timeout=5)
            if result:
                task_data = json.loads(result[1])
                # Помечаем как обрабатываемую
                redis_client.sadd(self.processing_set, task_data["task_id"])
                return task_data
        except Exception as e:
            logger.error(f"❌ Ошибка получения задачи: {e}")
        return None
    
    def complete_task(self, task_id: str, result: Dict):
        """Завершить задачу"""
        if not REDIS_AVAILABLE:
            return
            
        try:
            # Сохраняем результат
            redis_client.setex(
                f"{self.results_prefix}{task_id}",
                3600,  # 1 час TTL
                json.dumps(result)
            )
            # Убираем из обрабатываемых
            redis_client.srem(self.processing_set, task_id)
            logger.info(f"✅ Задача завершена: {task_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка завершения задачи: {e}")
    
    def get_task_result(self, task_id: str) -> Optional[Dict]:
        """Получить результат задачи"""
        if not REDIS_AVAILABLE:
            return None
            
        try:
            result = redis_client.get(f"{self.results_prefix}{task_id}")
            if result:
                return json.loads(result)
        except Exception as e:
            logger.error(f"❌ Ошибка получения результата: {e}")
        return None
    
    def get_queue_stats(self) -> Dict:
        """Статистика очереди"""
        if not REDIS_AVAILABLE:
            return {"queue_length": 0, "processing": 0}
            
        try:
            return {
                "queue_length": redis_client.llen(self.queue_name),
                "processing": redis_client.scard(self.processing_set),
                "redis_available": True
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {"queue_length": 0, "processing": 0, "redis_available": False}

# Глобальная очередь
task_queue = TaskQueue()

# Воркер для обработки задач
class VideoWorker:
    """Воркер для обработки видео задач"""
    
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.running = False
    
    async def start(self):
        """Запуск воркера"""
        self.running = True
        logger.info(f"🔄 Воркер {self.worker_id} запущен")
        
        while self.running:
            try:
                # Получаем задачу из очереди
                task = task_queue.get_task()
                if task:
                    await self.process_task(task)
                else:
                    # Если задач нет, ждем немного
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"❌ Ошибка воркера {self.worker_id}: {e}")
                await asyncio.sleep(5)
    
    async def process_task(self, task: Dict):
        """Обработка одной задачи"""
        task_id = task["task_id"]
        video_id = task["video_id"]
        
        try:
            logger.info(f"🎬 Воркер {self.worker_id} обрабатывает: {task_id}")
            
            # Здесь вызываем существующую функцию анализа
            result = await self.analyze_video_internal(video_id)
            
            # Сохраняем результат
            task_queue.complete_task(task_id, {
                "status": "completed",
                "result": result,
                "worker_id": self.worker_id,
                "completed_at": datetime.now().isoformat()
            })
            
        except Exception as e:
            # Сохраняем ошибку
            task_queue.complete_task(task_id, {
                "status": "failed",
                "error": str(e),
                "worker_id": self.worker_id,
                "failed_at": datetime.now().isoformat()
            })
    
    async def analyze_video_internal(self, video_id: str) -> Dict:
        """Внутренняя функция анализа (копия существующей логики)"""
        # Здесь копируем логику из analyze_video_task
        # но делаем её более легковесной
        
        # Находим видео файл
        video_files = [f for f in os.listdir(Config.UPLOAD_DIR) if f.startswith(video_id)]
        if not video_files:
            raise Exception("Видео файл не найден")
        
        video_path = os.path.join(Config.UPLOAD_DIR, video_files[0])
        
        # Извлечение аудио (оптимизированное)
        audio_path = os.path.join(Config.AUDIO_DIR, f"{video_id}.wav")
        if not extract_audio(video_path, audio_path):
            raise Exception("Ошибка извлечения аудио")
        
        # Транскрипция
        transcript_result = safe_transcribe_audio(audio_path)
        if not transcript_result:
            raise Exception("Ошибка транскрипции")
        
        # Анализ с ChatGPT
        video_duration = get_video_duration(video_path)
        
        if "words" in transcript_result:
            transcript_text = " ".join([word["word"] for word in transcript_result["words"]])
            transcript_words = transcript_result["words"]
        else:
            transcript_text = transcript_result.get("text", "")
            transcript_words = []
        
        analysis_result = analyze_with_chatgpt(transcript_text, video_duration)
        if not analysis_result:
            analysis_result = create_fallback_highlights(video_duration, 3)
        
        # Очистка временного аудио файла
        try:
            os.remove(audio_path)
        except:
            pass
        
        return {
            "highlights": analysis_result["highlights"],
            "transcript": transcript_words,
            "video_duration": video_duration
        }
    
    def stop(self):
        """Остановка воркера"""
        self.running = False
        logger.info(f"🛑 Воркер {self.worker_id} остановлен")

# Запуск воркеров в фоне
workers = []

async def start_workers(num_workers: int = 3):
    """Запуск нескольких воркеров"""
    global workers
    
    for i in range(num_workers):
        worker = VideoWorker(f"worker_{i+1}")
        workers.append(worker)
        # Запускаем в фоне
        asyncio.create_task(worker.start())
    
    logger.info(f"🚀 Запущено {num_workers} воркеров")

def stop_all_workers():
    """Остановка всех воркеров"""
    for worker in workers:
        worker.stop()
    workers.clear()