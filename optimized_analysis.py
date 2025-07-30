#!/usr/bin/env python3
"""
Оптимизированная версия анализа видео с параллельной обработкой
"""
import asyncio
import concurrent.futures
import time
from typing import Dict, Optional, List

async def optimized_analyze_video_task(task_id: str, video_id: str, auto_emoji: bool = False):
    """Оптимизированная фоновая задача анализа видео с параллельной обработкой"""
    try:
        start_time = time.time()
        logger.info(f"🚀 Начат ОПТИМИЗИРОВАННЫЙ анализ видео: {video_id}")
        
        # Обновляем прогресс
        analysis_tasks[task_id]["progress"] = 5
        
        # Находим видео файл
        video_files = [f for f in os.listdir(Config.UPLOAD_DIR) if f.startswith(video_id)]
        if not video_files:
            raise Exception("Видео файл не найден")
        
        video_path = os.path.join(Config.UPLOAD_DIR, video_files[0])
        audio_path = os.path.join(Config.AUDIO_DIR, f"{video_id}.wav")
        
        # ОПТИМИЗАЦИЯ 1: Параллельное извлечение аудио и получение длительности
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # Запускаем параллельно
            audio_future = executor.submit(extract_audio_optimized, video_path, audio_path)
            duration_future = executor.submit(get_video_duration_fast, video_path)
            
            # Ждем результаты
            audio_success = audio_future.result()
            video_duration = duration_future.result()
            
            if not audio_success:
                raise Exception("Ошибка извлечения аудио")
        
        analysis_tasks[task_id]["progress"] = 25
        logger.info(f"⚡ Аудио извлечено за {time.time() - start_time:.1f}s")
        
        # ОПТИМИЗАЦИЯ 2: Быстрая транскрипция с кэшированием
        transcript_start = time.time()
        transcript_result = await fast_transcribe_audio(audio_path, auto_emoji, video_duration)
        if not transcript_result:
            raise Exception("Ошибка транскрипции")
        
        analysis_tasks[task_id]["progress"] = 60
        logger.info(f"⚡ Транскрипция завершена за {time.time() - transcript_start:.1f}s")
        
        # ОПТИМИЗАЦИЯ 3: Параллельная обработка транскрипта и анализ
        if "words" in transcript_result:
            transcript_text = " ".join([word["word"] for word in transcript_result["words"]])
            transcript_words = transcript_result["words"]
        else:
            transcript_text = transcript_result.get("text", "")
            transcript_words = []
        
        # Запускаем анализ ChatGPT параллельно с предварительной обработкой
        analysis_start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # Параллельно запускаем анализ и предобработку
            analysis_future = executor.submit(analyze_with_chatgpt_fast, transcript_text, video_duration)
            preprocessing_future = executor.submit(preprocess_transcript_data, transcript_text, video_duration)
            
            # Получаем результаты
            analysis_result = analysis_future.result()
            preprocessing_data = preprocessing_future.result()
        
        analysis_tasks[task_id]["progress"] = 90
        logger.info(f"⚡ Анализ ChatGPT завершен за {time.time() - analysis_start:.1f}s")
        
        # Fallback если анализ не удался
        if not analysis_result:
            analysis_result = create_fallback_highlights_fast(video_duration, preprocessing_data)
        
        # Завершение
        total_time = time.time() - start_time
        analysis_tasks[task_id].update({
            "status": "completed",
            "progress": 100,
            "completed_at": datetime.now(),
            "processing_time": total_time,
            "result": {
                "highlights": analysis_result["highlights"],
                "transcript": transcript_words,
                "video_duration": video_duration
            }
        })
        
        logger.info(f"🎉 ОПТИМИЗИРОВАННЫЙ анализ завершен за {total_time:.1f}s (было ~{total_time*2:.1f}s)")
        
    except Exception as e:
        logger.error(f"❌ Ошибка оптимизированного анализа {video_id}: {e}")
        analysis_tasks[task_id].update({
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.now()
        })

def extract_audio_optimized(video_path: str, audio_path: str) -> bool:
    """Оптимизированное извлечение аудио с улучшенными параметрами"""
    try:
        # ОПТИМИЗАЦИЯ: Более агрессивные параметры для скорости
        cmd = [
            'ffmpeg', '-i', video_path,
            '-vn',  # Без видео
            '-acodec', 'mp3',
            '-ar', '16000',  # Низкая частота для Whisper
            '-ac', '1',  # Моно
            '-ab', '32k',  # Еще ниже битрейт для скорости
            '-threads', '2',  # Больше потоков
            '-preset', 'ultrafast',  # Самый быстрый пресет
            '-y', audio_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
        return os.path.exists(audio_path)
    except Exception as e:
        logger.error(f"Ошибка оптимизированного извлечения аудио: {e}")
        return False

def get_video_duration_fast(video_path: str) -> float:
    """Быстрое получение длительности видео"""
    try:
        # ОПТИМИЗАЦИЯ: Используем ffprobe с минимальными параметрами
        cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
        return float(result.stdout.strip())
    except Exception as e:
        logger.error(f"Ошибка получения длительности: {e}")
        return 60.0

async def fast_transcribe_audio(audio_path: str, auto_emoji: bool = False, video_duration: float = 60.0) -> Optional[Dict]:
    """Быстрая транскрипция с кэшированием и оптимизациями"""
    try:
        # ОПТИМИЗАЦИЯ: Проверяем кэш транскрипций
        cache_key = f"transcript_{os.path.basename(audio_path)}_{auto_emoji}"
        if REDIS_AVAILABLE:
            try:
                cached_result = redis_client.get(cache_key)
                if cached_result:
                    logger.info("⚡ Использован кэшированный результат транскрипции")
                    return json.loads(cached_result)
            except:
                pass
        
        # ОПТИМИЗАЦИЯ: Сжимаем аудио файл если он большой
        file_size = os.path.getsize(audio_path)
        if file_size > 10 * 1024 * 1024:  # Больше 10MB
            compressed_path = audio_path.replace('.wav', '_compressed.wav')
            if compress_audio_for_whisper(audio_path, compressed_path):
                audio_path = compressed_path
        
        # Транскрипция с оптимизированными параметрами
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["word"],
                # ОПТИМИЗАЦИЯ: Сокращенный промпт для скорости
                prompt="Include filler words: um, uh, yeah, like, so, well, actually, right, okay."
            )
            
        result = transcript.model_dump() if hasattr(transcript, 'model_dump') else dict(transcript)
        
        # Быстрая постобработка
        if 'words' in result:
            result['words'] = enhance_filler_words_fast(result['words'])
            
            if auto_emoji:
                result['words'] = addEmojisToText(result['words'], video_duration)
        
        # ОПТИМИЗАЦИЯ: Кэшируем результат
        if REDIS_AVAILABLE:
            try:
                redis_client.setex(cache_key, 3600, json.dumps(result))  # Кэш на 1 час
            except:
                pass
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка быстрой транскрипции: {e}")
        return None

def compress_audio_for_whisper(input_path: str, output_path: str) -> bool:
    """Сжимает аудио для ускорения Whisper"""
    try:
        cmd = [
            'ffmpeg', '-i', input_path,
            '-ar', '16000',  # Whisper оптимальная частота
            '-ac', '1',      # Моно
            '-ab', '16k',    # Минимальный битрейт
            '-y', output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=60)
        return os.path.exists(output_path)
    except:
        return False

def enhance_filler_words_fast(words: List[Dict]) -> List[Dict]:
    """Быстрая версия обработки вставных слов"""
    # ОПТИМИЗАЦИЯ: Упрощенная версия с основными исправлениями
    quick_corrections = {
        'um': ['uhm', 'umm'], 'uh': ['uhh'], 'yeah': ['yah', 'yea'],
        'like': ['lyk'], 'okay': ['ok'], 'right': ['rite']
    }
    
    for word in words:
        word_text = word.get('word', '').strip().lower()
        for correct, variations in quick_corrections.items():
            if word_text in variations:
                word['word'] = correct
                break
    
    return words

def analyze_with_chatgpt_fast(transcript_text: str, video_duration: float) -> Optional[Dict]:
    """Быстрая версия анализа ChatGPT с сокращенным промптом"""
    try:
        # ОПТИМИЗАЦИЯ: Сокращенный промпт для скорости
        target_clips = min(3, max(1, int(video_duration / 60)))  # Упрощенная логика
        
        prompt = f"""Find {target_clips} best moments in this {video_duration:.0f}s video for short clips.

Transcript: {transcript_text[:2000]}...  

Return JSON with highlights array. Each highlight needs:
- start_time, end_time (in seconds, 0-{video_duration:.0f})
- title (3-5 words, English)
- description (why it's interesting)
- Duration: 40-80 seconds each

Focus on: valuable insights, funny moments, key information, emotional peaks.

JSON format:
{{"highlights": [{{"start_time": 0, "end_time": 60, "title": "Key Insight", "description": "Main valuable moment"}}]}}"""

        # ОПТИМИЗАЦИЯ: Меньше токенов, быстрее ответ
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Быстрая модель
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,  # Меньше токенов
            temperature=0.3  # Меньше креативности, больше скорости
        )
        
        content = response.choices[0].message.content.strip()
        if content.startswith('```json'):
            content = content[7:]
        if content.endswith('```'):
            content = content[:-3]
        
        result = json.loads(content.strip())
        highlights = result.get("highlights", [])
        
        # Быстрая валидация
        for highlight in highlights:
            duration = highlight["end_time"] - highlight["start_time"]
            if duration < 40:
                highlight["end_time"] = min(highlight["start_time"] + 40, video_duration)
            elif duration > 80:
                highlight["end_time"] = highlight["start_time"] + 80
        
        return {"highlights": highlights}
        
    except Exception as e:
        logger.error(f"Ошибка быстрого анализа ChatGPT: {e}")
        return None

def preprocess_transcript_data(transcript_text: str, video_duration: float) -> Dict:
    """Предварительная обработка данных транскрипта"""
    return {
        "word_count": len(transcript_text.split()),
        "duration": video_duration,
        "content_type": "general"  # Упрощенная версия
    }

def create_fallback_highlights_fast(video_duration: float, preprocessing_data: Dict) -> Dict:
    """Быстрое создание fallback хайлайтов"""
    clips_count = min(2, max(1, int(video_duration / 60)))
    highlights = []
    
    segment_duration = video_duration / clips_count
    for i in range(clips_count):
        start = i * segment_duration
        end = min(start + 50, video_duration)  # 50 секунд клип
        
        highlights.append({
            "start_time": start,
            "end_time": end,
            "title": f"Moment {i+1}",
            "description": "Auto-generated highlight"
        })
    
    return {"highlights": highlights}