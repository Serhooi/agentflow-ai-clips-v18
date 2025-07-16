#!/usr/bin/env python3
# worker.py - Background Worker для обработки видео задач
import os
import sys
import asyncio
import logging
from datetime import datetime

# Добавляем текущую директорию в путь для импорта
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Импортируем функции из основного приложения
from app import (
    hybrid_queue, 
    Config,
    get_video_duration,
    extract_audio,
    safe_transcribe_audio,
    analyze_with_chatgpt,
    create_fallback_highlights,
    get_memory_usage,
    check_memory_limit,
    cleanup_old_files
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("worker")

class VideoWorker:
    """Воркер для обработки видео задач"""
    
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.running = False
        self.processed_count = 0
        self.error_count = 0
    
    async def start(self):
        """Запуск воркера"""
        self.running = True
        logger.info(f"🔄 Воркер {self.worker_id} запущен")
        
        # Проверяем память при старте
        memory_info = get_memory_usage()
        logger.info(f"💾 Память при старте: {memory_info['process_mb']}MB")
        
        while self.running:
            try:
                # Проверяем память перед обработкой
                if not check_memory_limit():
                    logger.warning(f"⚠️ Воркер {self.worker_id}: превышен лимит памяти")
                    cleanup_old_files()
                    await asyncio.sleep(10)
                    continue
                
                # Получаем задачу из очереди
                task = hybrid_queue.get_task()
                
                if task:
                    await self.process_task(task)
                else:
                    # Если задач нет, ждем немного
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"❌ Критическая ошибка воркера {self.worker_id}: {e}")
                self.error_count += 1
                await asyncio.sleep(5)
    
    async def process_task(self, task: dict):
        """Обработка одной задачи"""
        task_id = task["task_id"]
        video_id = task["video_id"]
        
        start_time = datetime.now()
        logger.info(f"🎬 Воркер {self.worker_id} обрабатывает: {task_id}")
        
        try:
            # Обрабатываем видео
            result = await self.analyze_video_internal(video_id)
            
            # Сохраняем результат
            hybrid_queue.complete_task(task_id, {
                "status": "completed",
                "result": result,
                "worker_id": self.worker_id,
                "processing_time": (datetime.now() - start_time).total_seconds(),
                "completed_at": datetime.now().isoformat()
            })
            
            self.processed_count += 1
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"✅ Воркер {self.worker_id} завершил {task_id} за {processing_time:.1f}s")
            
        except Exception as e:
            # Сохраняем ошибку
            hybrid_queue.complete_task(task_id, {
                "status": "failed",
                "error": str(e),
                "worker_id": self.worker_id,
                "processing_time": (datetime.now() - start_time).total_seconds(),
                "failed_at": datetime.now().isoformat()
            })
            
            self.error_count += 1
            logger.error(f"❌ Воркер {self.worker_id} ошибка в {task_id}: {e}")
    
    async def analyze_video_internal(self, video_id: str) -> dict:
        """Внутренняя функция анализа видео"""
        try:
            # Находим видео файл
            video_files = [f for f in os.listdir(Config.UPLOAD_DIR) if f.startswith(video_id)]
            if not video_files:
                raise Exception("Видео файл не найден")
            
            video_path = os.path.join(Config.UPLOAD_DIR, video_files[0])
            
            # Извлечение аудио
            audio_path = os.path.join(Config.AUDIO_DIR, f"{video_id}.wav")
            if not extract_audio(video_path, audio_path):
                raise Exception("Ошибка извлечения аудио")
            
            # Транскрипция
            transcript_result = safe_transcribe_audio(audio_path)
            if not transcript_result:
                raise Exception("Ошибка транскрипции")
            
            # Анализ с ChatGPT
            video_duration = get_video_duration(video_path)
            
            # Обработка структуры транскрипта
            if "words" in transcript_result:
                transcript_text = " ".join([word["word"] for word in transcript_result["words"]])
                transcript_words = transcript_result["words"]
            elif "segments" in transcript_result:
                transcript_text = " ".join([segment["text"] for segment in transcript_result["segments"]])
                transcript_words = []
                for segment in transcript_result["segments"]:
                    if "words" in segment:
                        transcript_words.extend(segment["words"])
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
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа видео {video_id}: {e}")
            raise
    
    def get_stats(self) -> dict:
        """Статистика воркера"""
        return {
            "worker_id": self.worker_id,
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            "running": self.running
        }
    
    def stop(self):
        """Остановка воркера"""
        self.running = False
        logger.info(f"🛑 Воркер {self.worker_id} остановлен")

async def main():
    """Главная функция воркера"""
    # Получаем ID воркера из переменной окружения или генерируем
    worker_id = os.getenv("WORKER_ID", f"worker_{os.getpid()}")
    
    # Создаем и запускаем воркера
    worker = VideoWorker(worker_id)
    
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал остановки")
        worker.stop()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        stats = worker.get_stats()
        logger.info(f"📊 Статистика воркера: {stats}")

if __name__ == "__main__":
    # Запуск воркера
    asyncio.run(main())