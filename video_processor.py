# video_processor.py - Обработка видео с FFmpeg и вшивание субтитров
# Создание видео с burned-in субтитрами в стиле Opus.pro

import os
import subprocess
import logging
from typing import Dict, List, Optional, Tuple
import json
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

class VideoProcessor:
    """Процессор видео для создания клипов с вшитыми субтитрами"""
    
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()
        self.supported_formats = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
        
    def check_ffmpeg(self) -> bool:
        """Проверяет доступность FFmpeg"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"FFmpeg недоступен: {e}")
            return False
    
    def get_video_info(self, video_path: str) -> Optional[Dict]:
        """Получает информацию о видео"""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                info = json.loads(result.stdout)
                
                # Находим видео поток
                video_stream = None
                for stream in info.get('streams', []):
                    if stream.get('codec_type') == 'video':
                        video_stream = stream
                        break
                
                if video_stream:
                    return {
                        'duration': float(info['format'].get('duration', 0)),
                        'width': int(video_stream.get('width', 0)),
                        'height': int(video_stream.get('height', 0)),
                        'fps': eval(video_stream.get('r_frame_rate', '30/1')),
                        'codec': video_stream.get('codec_name', 'unknown'),
                        'bitrate': int(info['format'].get('bit_rate', 0))
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения информации о видео: {e}")
            return None
    
    def create_subtitle_filter(self, subtitle_data: Dict, style: str = "modern", 
                             position: str = "bottom") -> str:
        """Создает FFmpeg фильтр для субтитров"""
        
        # Базовые настройки стиля
        styles = {
            "modern": {
                "fontfile": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "fontsize": "24",
                "fontcolor": "white",
                "borderw": "2",
                "bordercolor": "black",
                "shadowcolor": "black@0.5",
                "shadowx": "2",
                "shadowy": "2"
            },
            "classic": {
                "fontfile": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "fontsize": "20",
                "fontcolor": "white",
                "borderw": "1",
                "bordercolor": "black"
            },
            "neon": {
                "fontfile": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "fontsize": "26",
                "fontcolor": "cyan",
                "borderw": "3",
                "bordercolor": "blue",
                "shadowcolor": "cyan@0.8",
                "shadowx": "0",
                "shadowy": "0"
            },
            "minimal": {
                "fontfile": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "fontsize": "18",
                "fontcolor": "white",
                "borderw": "1",
                "bordercolor": "black"
            }
        }
        
        style_config = styles.get(style, styles["modern"])
        
        # Позиционирование
        if position == "bottom":
            y_position = "h-th-20"
        elif position == "top":
            y_position = "20"
        else:  # center
            y_position = "(h-th)/2"
        
        # Создаем фильтр
        filter_parts = []
        filter_parts.append(f"fontfile={style_config['fontfile']}")
        filter_parts.append(f"fontsize={style_config['fontsize']}")
        filter_parts.append(f"fontcolor={style_config['fontcolor']}")
        filter_parts.append(f"borderw={style_config['borderw']}")
        filter_parts.append(f"bordercolor={style_config['bordercolor']}")
        filter_parts.append(f"x=(w-tw)/2")  # Центрирование по горизонтали
        filter_parts.append(f"y={y_position}")
        
        if "shadowcolor" in style_config:
            filter_parts.append(f"shadowcolor={style_config['shadowcolor']}")
            filter_parts.append(f"shadowx={style_config['shadowx']}")
            filter_parts.append(f"shadowy={style_config['shadowy']}")
        
        return ":".join(filter_parts)
    
    def create_karaoke_video(self, video_path: str, subtitle_data: Dict, 
                           output_path: str, style: str = "modern",
                           position: str = "bottom") -> bool:
        """Создает видео с караоке-субтитрами"""
        try:
            if not self.check_ffmpeg():
                logger.error("FFmpeg недоступен")
                return False
            
            # Создаем временный файл субтитров
            temp_srt = os.path.join(self.temp_dir, f"temp_subtitles_{os.getpid()}.srt")
            
            # Генерируем SRT файл
            if not self._create_srt_file(subtitle_data, temp_srt):
                return False
            
            try:
                # Получаем информацию о видео
                video_info = self.get_video_info(video_path)
                if not video_info:
                    logger.error("Не удалось получить информацию о видео")
                    return False
                
                # Создаем фильтр субтитров
                subtitle_filter = self.create_subtitle_filter(subtitle_data, style, position)
                
                # Команда FFmpeg
                cmd = [
                    'ffmpeg', '-y',  # Перезаписывать выходной файл
                    '-i', video_path,  # Входное видео
                    '-vf', f"subtitles={temp_srt}:{subtitle_filter}",  # Фильтр субтитров
                    '-c:a', 'copy',  # Копировать аудио без перекодирования
                    '-c:v', 'libx264',  # Видео кодек
                    '-preset', 'medium',  # Баланс скорости/качества
                    '-crf', '23',  # Качество видео
                    output_path
                ]
                
                logger.info(f"🔄 Создание видео с субтитрами: {output_path}")
                
                # Выполняем команду
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0:
                    logger.info(f"✅ Видео с субтитрами создано: {output_path}")
                    return True
                else:
                    logger.error(f"❌ Ошибка FFmpeg: {result.stderr}")
                    return False
                    
            finally:
                # Удаляем временный файл
                if os.path.exists(temp_srt):
                    os.remove(temp_srt)
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания видео с субтитрами: {e}")
            return False
    
    def create_clip_with_subtitles(self, video_path: str, start_time: float, 
                                 end_time: float, subtitle_data: Dict,
                                 output_path: str, style: str = "modern") -> bool:
        """Создает клип с субтитрами"""
        try:
            if not self.check_ffmpeg():
                return False
            
            # Фильтруем субтитры для данного временного отрезка
            clip_subtitles = self._filter_subtitles_for_clip(
                subtitle_data, start_time, end_time
            )
            
            # Создаем временный файл субтитров
            temp_srt = os.path.join(self.temp_dir, f"clip_subtitles_{os.getpid()}.srt")
            
            if not self._create_srt_file(clip_subtitles, temp_srt):
                return False
            
            try:
                # Создаем фильтр субтитров
                subtitle_filter = self.create_subtitle_filter(clip_subtitles, style)
                
                # Команда FFmpeg для создания клипа
                cmd = [
                    'ffmpeg', '-y',
                    '-i', video_path,
                    '-ss', str(start_time),  # Начальное время
                    '-t', str(end_time - start_time),  # Длительность
                    '-vf', f"subtitles={temp_srt}:{subtitle_filter}",
                    '-c:a', 'copy',
                    '-c:v', 'libx264',
                    '-preset', 'medium',
                    '-crf', '23',
                    output_path
                ]
                
                logger.info(f"🔄 Создание клипа с субтитрами: {start_time}-{end_time}s")
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                
                if result.returncode == 0:
                    logger.info(f"✅ Клип создан: {output_path}")
                    return True
                else:
                    logger.error(f"❌ Ошибка создания клипа: {result.stderr}")
                    return False
                    
            finally:
                if os.path.exists(temp_srt):
                    os.remove(temp_srt)
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания клипа: {e}")
            return False
    
    def _create_srt_file(self, subtitle_data: Dict, output_path: str) -> bool:
        """Создает SRT файл из данных субтитров"""
        try:
            content = ""
            
            if 'segments' in subtitle_data:
                for i, segment in enumerate(subtitle_data['segments'], 1):
                    start_time = self._format_srt_time(segment['start'])
                    end_time = self._format_srt_time(segment['end'])
                    text = segment['text'].strip()
                    
                    content += f"{i}\n"
                    content += f"{start_time} --> {end_time}\n"
                    content += f"{text}\n\n"
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка создания SRT файла: {e}")
            return False
    
    def _format_srt_time(self, seconds: float) -> str:
        """Форматирует время для SRT"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        milliseconds = int((secs % 1) * 1000)
        secs = int(secs)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
    
    def _filter_subtitles_for_clip(self, subtitle_data: Dict, 
                                 start_time: float, end_time: float) -> Dict:
        """Фильтрует субтитры для конкретного клипа"""
        filtered_data = {
            "text": "",
            "segments": []
        }
        
        if 'segments' not in subtitle_data:
            return filtered_data
        
        for segment in subtitle_data['segments']:
            seg_start = segment['start']
            seg_end = segment['end']
            
            # Проверяем пересечение с временным отрезком клипа
            if seg_end > start_time and seg_start < end_time:
                # Корректируем времена относительно начала клипа
                new_segment = segment.copy()
                new_segment['start'] = max(0, seg_start - start_time)
                new_segment['end'] = min(end_time - start_time, seg_end - start_time)
                
                # Корректируем времена слов если есть
                if 'words' in new_segment and new_segment['words']:
                    new_words = []
                    for word in new_segment['words']:
                        if word['end'] > start_time and word['start'] < end_time:
                            new_word = word.copy()
                            new_word['start'] = max(0, word['start'] - start_time)
                            new_word['end'] = min(end_time - start_time, word['end'] - start_time)
                            new_words.append(new_word)
                    new_segment['words'] = new_words
                
                filtered_data['segments'].append(new_segment)
        
        return filtered_data
    
    def optimize_video_for_web(self, input_path: str, output_path: str) -> bool:
        """Оптимизирует видео для веба"""
        try:
            cmd = [
                'ffmpeg', '-y',
                '-i', input_path,
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '28',
                '-maxrate', '1M',
                '-bufsize', '2M',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-movflags', '+faststart',  # Для быстрого старта воспроизведения
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                logger.info(f"✅ Видео оптимизировано для веба: {output_path}")
                return True
            else:
                logger.error(f"❌ Ошибка оптимизации: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка оптимизации видео: {e}")
            return False

# Функции для интеграции с основным приложением
def create_video_with_subtitles(video_path: str, subtitle_data: Dict,
                               output_path: str, style: str = "modern") -> bool:
    """Создает видео с вшитыми субтитрами"""
    processor = VideoProcessor()
    return processor.create_karaoke_video(video_path, subtitle_data, output_path, style)

def create_clip_with_karaoke(video_path: str, start_time: float, end_time: float,
                           subtitle_data: Dict, output_path: str, 
                           style: str = "modern") -> bool:
    """Создает клип с караоке-субтитрами"""
    processor = VideoProcessor()
    return processor.create_clip_with_subtitles(
        video_path, start_time, end_time, subtitle_data, output_path, style
    )

