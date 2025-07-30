#!/usr/bin/env python3
"""
Система кэширования для ускорения анализа видео
"""
import hashlib
import json
import os
from typing import Dict, Optional

class VideoAnalysisCache:
    """Кэш для результатов анализа видео"""
    
    def __init__(self):
        self.cache_dir = "cache"
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def get_video_hash(self, video_path: str) -> str:
        """Получает хэш видео файла для кэширования"""
        try:
            # Используем размер файла + первые 1KB для быстрого хэша
            file_size = os.path.getsize(video_path)
            with open(video_path, 'rb') as f:
                first_chunk = f.read(1024)
            
            hash_data = f"{file_size}_{hashlib.md5(first_chunk).hexdigest()}"
            return hashlib.sha256(hash_data.encode()).hexdigest()[:16]
        except:
            return None
    
    def get_cached_transcript(self, video_path: str, auto_emoji: bool = False) -> Optional[Dict]:
        """Получает кэшированную транскрипцию"""
        video_hash = self.get_video_hash(video_path)
        if not video_hash:
            return None
        
        cache_file = os.path.join(self.cache_dir, f"transcript_{video_hash}_{auto_emoji}.json")
        
        try:
            if os.path.exists(cache_file):
                # Проверяем возраст кэша (не старше 24 часов)
                cache_age = time.time() - os.path.getmtime(cache_file)
                if cache_age < 24 * 3600:  # 24 часа
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        logger.info(f"⚡ Использован кэшированный транскрипт: {video_hash}")
                        return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка чтения кэша транскрипта: {e}")
        
        return None
    
    def cache_transcript(self, video_path: str, transcript_result: Dict, auto_emoji: bool = False):
        """Кэширует результат транскрипции"""
        video_hash = self.get_video_hash(video_path)
        if not video_hash:
            return
        
        cache_file = os.path.join(self.cache_dir, f"transcript_{video_hash}_{auto_emoji}.json")
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(transcript_result, f, ensure_ascii=False)
            logger.info(f"💾 Транскрипт сохранен в кэш: {video_hash}")
        except Exception as e:
            logger.error(f"Ошибка сохранения кэша транскрипта: {e}")
    
    def get_cached_analysis(self, transcript_text: str, video_duration: float) -> Optional[Dict]:
        """Получает кэшированный анализ ChatGPT"""
        # Создаем хэш на основе текста и длительности
        text_hash = hashlib.md5(transcript_text.encode()).hexdigest()[:16]
        cache_key = f"analysis_{text_hash}_{int(video_duration)}"
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        
        try:
            if os.path.exists(cache_file):
                cache_age = time.time() - os.path.getmtime(cache_file)
                if cache_age < 12 * 3600:  # 12 часов для анализа
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        logger.info(f"⚡ Использован кэшированный анализ: {cache_key}")
                        return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка чтения кэша анализа: {e}")
        
        return None
    
    def cache_analysis(self, transcript_text: str, video_duration: float, analysis_result: Dict):
        """Кэширует результат анализа ChatGPT"""
        text_hash = hashlib.md5(transcript_text.encode()).hexdigest()[:16]
        cache_key = f"analysis_{text_hash}_{int(video_duration)}"
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(analysis_result, f, ensure_ascii=False)
            logger.info(f"💾 Анализ сохранен в кэш: {cache_key}")
        except Exception as e:
            logger.error(f"Ошибка сохранения кэша анализа: {e}")
    
    def cleanup_old_cache(self):
        """Очищает старый кэш"""
        try:
            current_time = time.time()
            cleaned = 0
            
            for filename in os.listdir(self.cache_dir):
                file_path = os.path.join(self.cache_dir, filename)
                if os.path.isfile(file_path):
                    file_age = current_time - os.path.getmtime(file_path)
                    if file_age > 48 * 3600:  # Старше 48 часов
                        os.remove(file_path)
                        cleaned += 1
            
            if cleaned > 0:
                logger.info(f"🧹 Очищено {cleaned} старых файлов кэша")
        except Exception as e:
            logger.error(f"Ошибка очистки кэша: {e}")

# Глобальный экземпляр кэша
video_cache = VideoAnalysisCache()

def safe_transcribe_audio_cached(audio_path: str, video_path: str, auto_emoji: bool = False, video_duration: float = 60.0) -> Optional[Dict]:
    """Транскрипция с кэшированием"""
    
    # Проверяем кэш
    cached_result = video_cache.get_cached_transcript(video_path, auto_emoji)
    if cached_result:
        return cached_result
    
    # Если кэша нет, выполняем транскрипцию
    result = safe_transcribe_audio(audio_path, auto_emoji, video_duration)
    
    # Сохраняем в кэш
    if result:
        video_cache.cache_transcript(video_path, result, auto_emoji)
    
    return result

def analyze_with_chatgpt_cached(transcript_text: str, video_duration: float) -> Optional[Dict]:
    """Анализ ChatGPT с кэшированием"""
    
    # Проверяем кэш
    cached_result = video_cache.get_cached_analysis(transcript_text, video_duration)
    if cached_result:
        return cached_result
    
    # Если кэша нет, выполняем анализ
    result = analyze_with_chatgpt(transcript_text, video_duration)
    
    # Сохраняем в кэш
    if result:
        video_cache.cache_analysis(transcript_text, video_duration, result)
    
    return result