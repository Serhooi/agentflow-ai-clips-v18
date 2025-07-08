#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Video Burner - Модуль для создания видео с вшитыми субтитрами
"""

import os
import json
import subprocess
import tempfile
from typing import Dict, List, Any, Optional

class VideoBurner:
    """Класс для создания видео с вшитыми субтитрами"""
    
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        """Инициализация с путем к FFmpeg"""
        self.ffmpeg_path = ffmpeg_path
    
    def burn_subtitles(self, 
                      video_path: str, 
                      subtitle_path: str, 
                      output_path: str,
                      font_size: int = 24,
                      font_color: str = "white",
                      font_outline: int = 2,
                      quality: str = "medium") -> bool:
        """
        Создание видео с вшитыми субтитрами
        
        Args:
            video_path: Путь к исходному видео
            subtitle_path: Путь к файлу субтитров (ASS или SRT)
            output_path: Путь для сохранения результата
            font_size: Размер шрифта (для SRT)
            font_color: Цвет шрифта (для SRT)
            font_outline: Толщина обводки (для SRT)
            quality: Качество кодирования (low, medium, high)
            
        Returns:
            bool: True если успешно, False в случае ошибки
        """
        try:
            # Определяем пресет качества
            if quality == "low":
                preset = "veryfast"
                crf = "28"
            elif quality == "high":
                preset = "slow"
                crf = "18"
            else:  # medium
                preset = "medium"
                crf = "23"
            
            # Определяем тип субтитров
            subtitle_ext = os.path.splitext(subtitle_path)[1].lower()
            
            # Команда FFmpeg
            cmd = [
                self.ffmpeg_path,
                "-i", video_path,
                "-vf", f"subtitles={subtitle_path}:force_style='FontSize={font_size},PrimaryColour=&H{font_color},Outline={font_outline}'",
                "-c:v", "libx264",
                "-preset", preset,
                "-crf", crf,
                "-c:a", "aac",
                "-b:a", "128k",
                "-y",
                output_path
            ]
            
            # Запускаем процесс
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Получаем вывод
            stdout, stderr = process.communicate()
            
            # Проверяем результат
            if process.returncode != 0:
                print(f"Ошибка FFmpeg: {stderr}")
                return False
            
            return os.path.exists(output_path)
            
        except Exception as e:
            print(f"Ошибка при создании видео с субтитрами: {e}")
            return False
    
    def create_karaoke_video(self,
                           video_path: str,
                           transcript: Dict[str, Any],
                           output_path: str,
                           style: str = "modern",
                           quality: str = "medium") -> bool:
        """
        Создание караоке-видео из транскрипта
        
        Args:
            video_path: Путь к исходному видео
            transcript: Транскрипт в формате Whisper
            output_path: Путь для сохранения результата
            style: Стиль субтитров (default, karaoke, modern)
            quality: Качество кодирования (low, medium, high)
            
        Returns:
            bool: True если успешно, False в случае ошибки
        """
        try:
            # Создаем временный файл для субтитров
            with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as temp_file:
                temp_subtitle_path = temp_file.name
            
            # Генерируем ASS субтитры
            from ass_generator import ASSGenerator
            ass_generator = ASSGenerator()
            ass_content = ass_generator.generate_from_whisper(transcript, style)
            
            # Записываем во временный файл
            with open(temp_subtitle_path, "w", encoding="utf-8") as f:
                f.write(ass_content)
            
            # Создаем видео с субтитрами
            result = self.burn_subtitles(
                video_path=video_path,
                subtitle_path=temp_subtitle_path,
                output_path=output_path,
                quality=quality
            )
            
            # Удаляем временный файл
            try:
                os.unlink(temp_subtitle_path)
            except:
                pass
            
            return result
            
        except Exception as e:
            print(f"Ошибка при создании караоке-видео: {e}")
            return False

