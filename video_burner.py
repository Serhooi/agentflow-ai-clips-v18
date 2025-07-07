# video_burner.py - Модуль для создания видео с вшитыми субтитрами
# Использует FFmpeg для создания видео с субтитрами как в Opus.pro

import os
import subprocess
import logging
import tempfile
import json
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import shutil

logger = logging.getLogger(__name__)

class VideoBurner:
    """Класс для создания видео с вшитыми субтитрами"""
    
    def __init__(self):
        self.ffmpeg_path = self._find_ffmpeg()
        self.temp_dir = tempfile.gettempdir()
        
    def _find_ffmpeg(self) -> str:
        """Находит путь к FFmpeg"""
        # Проверяем стандартные пути
        possible_paths = [
            'ffmpeg',
            '/usr/bin/ffmpeg',
            '/usr/local/bin/ffmpeg',
            '/opt/homebrew/bin/ffmpeg'
        ]
        
        for path in possible_paths:
            try:
                result = subprocess.run([path, '-version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=10)
                if result.returncode == 0:
                    logger.info(f"FFmpeg найден: {path}")
                    return path
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
        
        raise RuntimeError("FFmpeg не найден в системе")

    def get_video_info(self, video_path: str) -> Dict[str, Any]:
        """Получает информацию о видео"""
        try:
            cmd = [
                self.ffmpeg_path, '-i', video_path,
                '-f', 'null', '-',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format', '-show_streams'
            ]
            
            # Используем ffprobe вместо ffmpeg для получения информации
            ffprobe_cmd = [
                'ffprobe', '-v', 'quiet',
                '-print_format', 'json',
                '-show_format', '-show_streams',
                video_path
            ]
            
            result = subprocess.run(ffprobe_cmd, 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=30)
            
            if result.returncode != 0:
                raise RuntimeError(f"Ошибка получения информации о видео: {result.stderr}")
            
            info = json.loads(result.stdout)
            
            # Извлекаем основную информацию
            video_stream = None
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break
            
            if not video_stream:
                raise RuntimeError("Видео поток не найден")
            
            return {
                'width': int(video_stream.get('width', 1920)),
                'height': int(video_stream.get('height', 1080)),
                'duration': float(info.get('format', {}).get('duration', 0)),
                'fps': eval(video_stream.get('r_frame_rate', '30/1')),
                'codec': video_stream.get('codec_name', 'unknown')
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения информации о видео: {str(e)}")
            # Возвращаем значения по умолчанию
            return {
                'width': 1920,
                'height': 1080,
                'duration': 60,
                'fps': 30,
                'codec': 'h264'
            }

    def create_subtitle_filter(self, ass_path: str, video_info: Dict[str, Any]) -> str:
        """Создает фильтр субтитров для FFmpeg"""
        # Экранируем путь для FFmpeg
        escaped_path = ass_path.replace('\\', '\\\\').replace(':', '\\:')
        
        # Базовый фильтр субтитров
        subtitle_filter = f"ass='{escaped_path}'"
        
        return subtitle_filter

    def create_advanced_subtitle_filter(self, 
                                      ass_path: str, 
                                      video_info: Dict[str, Any],
                                      style_options: Dict[str, Any] = None) -> str:
        """Создает продвинутый фильтр субтитров с дополнительными эффектами"""
        if style_options is None:
            style_options = {}
        
        # Экранируем путь
        escaped_path = ass_path.replace('\\', '\\\\').replace(':', '\\:')
        
        # Базовый фильтр
        filters = [f"ass='{escaped_path}'"]
        
        # Добавляем эффекты если указаны
        if style_options.get('blur_background'):
            # Размытие фона под субтитрами
            filters.insert(0, "boxblur=2:1")
        
        if style_options.get('enhance_contrast'):
            # Улучшение контраста
            filters.append("eq=contrast=1.2:brightness=0.1")
        
        if style_options.get('shadow_effect'):
            # Эффект тени (уже в ASS, но можно усилить)
            pass
        
        return ",".join(filters)

    def burn_subtitles(self, 
                      video_path: str, 
                      ass_path: str, 
                      output_path: str,
                      quality: str = "high",
                      style_options: Dict[str, Any] = None,
                      progress_callback: Optional[callable] = None) -> str:
        """
        Создает видео с вшитыми субтитрами
        
        Args:
            video_path: Путь к исходному видео
            ass_path: Путь к ASS файлу субтитров
            output_path: Путь для сохранения результата
            quality: Качество видео (low, medium, high, ultra)
            style_options: Дополнительные опции стиля
            progress_callback: Функция для отслеживания прогресса
            
        Returns:
            Путь к созданному видео
        """
        try:
            # Проверяем существование файлов
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Видео файл не найден: {video_path}")
            
            if not os.path.exists(ass_path):
                raise FileNotFoundError(f"ASS файл не найден: {ass_path}")
            
            # Получаем информацию о видео
            video_info = self.get_video_info(video_path)
            logger.info(f"Информация о видео: {video_info}")
            
            # Создаем директорию для выходного файла
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Настройки качества
            quality_settings = self._get_quality_settings(quality, video_info)
            
            # Создаем фильтр субтитров
            if style_options:
                subtitle_filter = self.create_advanced_subtitle_filter(
                    ass_path, video_info, style_options
                )
            else:
                subtitle_filter = self.create_subtitle_filter(ass_path, video_info)
            
            # Строим команду FFmpeg
            cmd = [
                self.ffmpeg_path,
                '-i', video_path,
                '-vf', subtitle_filter,
                '-c:v', quality_settings['video_codec'],
                '-c:a', quality_settings['audio_codec'],
                '-b:v', quality_settings['video_bitrate'],
                '-b:a', quality_settings['audio_bitrate'],
                '-preset', quality_settings['preset'],
                '-crf', str(quality_settings['crf']),
                '-movflags', '+faststart',  # Для быстрого старта воспроизведения
                '-y',  # Перезаписать выходной файл
                output_path
            ]
            
            logger.info(f"Команда FFmpeg: {' '.join(cmd)}")
            
            # Запускаем FFmpeg
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True
            )
            
            # Отслеживаем прогресс
            if progress_callback:
                self._monitor_progress(process, video_info['duration'], progress_callback)
            
            # Ждем завершения
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Ошибка FFmpeg: {stderr}")
                raise RuntimeError(f"Ошибка создания видео с субтитрами: {stderr}")
            
            # Проверяем, что файл создан
            if not os.path.exists(output_path):
                raise RuntimeError("Выходной файл не был создан")
            
            logger.info(f"Видео с субтитрами создано: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Ошибка создания видео с субтитрами: {str(e)}")
            raise

    def _get_quality_settings(self, quality: str, video_info: Dict[str, Any]) -> Dict[str, Any]:
        """Возвращает настройки качества для FFmpeg"""
        base_settings = {
            'video_codec': 'libx264',
            'audio_codec': 'aac',
            'preset': 'medium'
        }
        
        if quality == "low":
            return {
                **base_settings,
                'video_bitrate': '500k',
                'audio_bitrate': '64k',
                'crf': 28,
                'preset': 'fast'
            }
        elif quality == "medium":
            return {
                **base_settings,
                'video_bitrate': '1000k',
                'audio_bitrate': '128k',
                'crf': 23,
                'preset': 'medium'
            }
        elif quality == "high":
            return {
                **base_settings,
                'video_bitrate': '2000k',
                'audio_bitrate': '192k',
                'crf': 20,
                'preset': 'slow'
            }
        elif quality == "ultra":
            return {
                **base_settings,
                'video_bitrate': '4000k',
                'audio_bitrate': '256k',
                'crf': 18,
                'preset': 'slower'
            }
        else:
            # По умолчанию - высокое качество
            return {
                **base_settings,
                'video_bitrate': '2000k',
                'audio_bitrate': '192k',
                'crf': 20,
                'preset': 'slow'
            }

    def _monitor_progress(self, process: subprocess.Popen, 
                         total_duration: float, 
                         progress_callback: callable):
        """Отслеживает прогресс обработки FFmpeg"""
        try:
            while True:
                output = process.stderr.readline()
                if output == '' and process.poll() is not None:
                    break
                
                if output:
                    # Ищем информацию о времени в выводе FFmpeg
                    if 'time=' in output:
                        try:
                            time_str = output.split('time=')[1].split()[0]
                            # Парсим время в формате HH:MM:SS.mmm
                            time_parts = time_str.split(':')
                            if len(time_parts) == 3:
                                hours = float(time_parts[0])
                                minutes = float(time_parts[1])
                                seconds = float(time_parts[2])
                                current_time = hours * 3600 + minutes * 60 + seconds
                                
                                # Вычисляем прогресс в процентах
                                if total_duration > 0:
                                    progress = min(100, (current_time / total_duration) * 100)
                                    progress_callback(progress)
                        except (IndexError, ValueError):
                            pass
        except Exception as e:
            logger.warning(f"Ошибка отслеживания прогресса: {str(e)}")

    def create_preview_video(self, 
                           video_path: str, 
                           ass_path: str, 
                           output_path: str,
                           start_time: float = 0,
                           duration: float = 10) -> str:
        """
        Создает превью видео с субтитрами (короткий отрезок)
        
        Args:
            video_path: Путь к исходному видео
            ass_path: Путь к ASS файлу
            output_path: Путь для сохранения превью
            start_time: Время начала превью (секунды)
            duration: Длительность превью (секунды)
            
        Returns:
            Путь к созданному превью
        """
        try:
            # Получаем информацию о видео
            video_info = self.get_video_info(video_path)
            
            # Создаем фильтр субтитров
            subtitle_filter = self.create_subtitle_filter(ass_path, video_info)
            
            # Команда для создания превью
            cmd = [
                self.ffmpeg_path,
                '-ss', str(start_time),  # Начальное время
                '-i', video_path,
                '-t', str(duration),     # Длительность
                '-vf', subtitle_filter,
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-preset', 'fast',
                '-crf', '23',
                '-movflags', '+faststart',
                '-y',
                output_path
            ]
            
            logger.info(f"Создание превью: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=60)
            
            if result.returncode != 0:
                raise RuntimeError(f"Ошибка создания превью: {result.stderr}")
            
            logger.info(f"Превью создано: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Ошибка создания превью: {str(e)}")
            raise

    def batch_burn_subtitles(self, 
                           video_clips: List[Dict[str, str]], 
                           ass_path: str,
                           output_dir: str,
                           quality: str = "high") -> List[str]:
        """
        Массовое создание видео с субтитрами для нескольких клипов
        
        Args:
            video_clips: Список словарей с путями к клипам
            ass_path: Путь к ASS файлу
            output_dir: Директория для сохранения результатов
            quality: Качество видео
            
        Returns:
            Список путей к созданным видео
        """
        results = []
        
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            for i, clip_info in enumerate(video_clips):
                clip_path = clip_info.get('path')
                clip_name = clip_info.get('name', f'clip_{i}')
                
                if not clip_path or not os.path.exists(clip_path):
                    logger.warning(f"Клип не найден: {clip_path}")
                    continue
                
                # Создаем имя выходного файла
                output_filename = f"{clip_name}_with_subtitles.mp4"
                output_path = os.path.join(output_dir, output_filename)
                
                try:
                    # Создаем видео с субтитрами
                    result_path = self.burn_subtitles(
                        clip_path, ass_path, output_path, quality
                    )
                    results.append(result_path)
                    logger.info(f"Клип обработан: {result_path}")
                    
                except Exception as e:
                    logger.error(f"Ошибка обработки клипа {clip_name}: {str(e)}")
                    continue
            
            return results
            
        except Exception as e:
            logger.error(f"Ошибка массовой обработки: {str(e)}")
            raise

# Пример использования
if __name__ == "__main__":
    # Тестирование модуля
    burner = VideoBurner()
    
    # Тестовые пути (замените на реальные)
    video_path = "/tmp/test_video.mp4"
    ass_path = "/tmp/test_subtitles.ass"
    output_path = "/tmp/output_with_subtitles.mp4"
    
    if os.path.exists(video_path) and os.path.exists(ass_path):
        try:
            # Создаем видео с субтитрами
            result = burner.burn_subtitles(
                video_path, 
                ass_path, 
                output_path,
                quality="high"
            )
            print(f"Видео с субтитрами создано: {result}")
            
            # Создаем превью
            preview_path = "/tmp/preview_with_subtitles.mp4"
            preview_result = burner.create_preview_video(
                video_path,
                ass_path,
                preview_path,
                start_time=10,
                duration=5
            )
            print(f"Превью создано: {preview_result}")
            
        except Exception as e:
            print(f"Ошибка: {str(e)}")
    else:
        print("Тестовые файлы не найдены")

