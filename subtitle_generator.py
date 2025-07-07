# subtitle_generator.py - Генерация ASS субтитров с караоке-эффектом
# Интеграция с auto-karaoke для профессиональных субтитров

import os
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import timedelta
import re

logger = logging.getLogger(__name__)

class KaraokeSubtitleGenerator:
    """Генератор караоке-субтитров в формате ASS"""
    
    def __init__(self):
        self.default_style = {
            'font_name': 'Arial',
            'font_size': 20,
            'primary_color': '&H00FFFFFF',  # Белый
            'secondary_color': '&H000000FF',  # Красный (для караоке)
            'outline_color': '&H00000000',   # Черный контур
            'back_color': '&H80000000',      # Полупрозрачный черный фон
            'bold': True,
            'italic': False,
            'underline': False,
            'strike_out': False,
            'scale_x': 100,
            'scale_y': 100,
            'spacing': 0,
            'angle': 0,
            'border_style': 1,
            'outline': 2,
            'shadow': 0,
            'alignment': 2,  # Центр снизу
            'margin_l': 10,
            'margin_r': 10,
            'margin_v': 10
        }
    
    def format_time(self, seconds: float) -> str:
        """Конвертирует секунды в формат времени ASS (H:MM:SS.CC)"""
        td = timedelta(seconds=seconds)
        hours = int(td.total_seconds() // 3600)
        minutes = int((td.total_seconds() % 3600) // 60)
        secs = td.total_seconds() % 60
        centiseconds = int((secs % 1) * 100)
        secs = int(secs)
        
        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"
    
    def create_ass_header(self, style: Optional[Dict] = None) -> str:
        """Создает заголовок ASS файла"""
        if style is None:
            style = self.default_style
            
        header = f"""[Script Info]
Title: AgentFlow AI Clips - Karaoke Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style['font_name']},{style['font_size']},{style['primary_color']},{style['secondary_color']},{style['outline_color']},{style['back_color']},{-1 if style['bold'] else 0},{-1 if style['italic'] else 0},{-1 if style['underline'] else 0},{-1 if style['strike_out'] else 0},{style['scale_x']},{style['scale_y']},{style['spacing']},{style['angle']},{style['border_style']},{style['outline']},{style['shadow']},{style['alignment']},{style['margin_l']},{style['margin_r']},{style['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        return header
    
    def create_karaoke_line(self, segment: Dict, style_name: str = "Default") -> List[str]:
        """Создает строки ASS с караоке-эффектом для сегмента"""
        lines = []
        
        start_time = self.format_time(segment['start'])
        end_time = self.format_time(segment['end'])
        
        # Если есть word-level тайминги, создаем караоке-эффект
        if 'words' in segment and segment['words']:
            karaoke_text = self.create_karaoke_text(segment['words'], segment['start'])
            line = f"Dialogue: 0,{start_time},{end_time},{style_name},,0,0,0,,{karaoke_text}"
            lines.append(line)
        else:
            # Простой текст без караоке
            text = segment['text'].strip()
            line = f"Dialogue: 0,{start_time},{end_time},{style_name},,0,0,0,,{text}"
            lines.append(line)
        
        return lines
    
    def create_karaoke_text(self, words: List[Dict], segment_start: float) -> str:
        """Создает текст с караоке-тегами для ASS"""
        karaoke_parts = []
        
        for i, word in enumerate(words):
            word_text = word['word'].strip()
            if not word_text:
                continue
                
            # Вычисляем длительность слова в сантисекундах
            word_duration = (word['end'] - word['start']) * 100
            word_duration = max(10, int(word_duration))  # Минимум 10 сантисекунд
            
            # Добавляем караоке-тег
            karaoke_parts.append(f"{{\\k{word_duration}}}{word_text}")
        
        return "".join(karaoke_parts)
    
    def create_modern_karaoke_text(self, words: List[Dict], segment_start: float) -> str:
        """Создает современный караоке-эффект с цветовыми переходами"""
        karaoke_parts = []
        
        # Цвета для градиента (в формате BGR для ASS)
        colors = [
            "&H00FFD700",  # Золотой
            "&H0000BFFF",  # Голубой
            "&H00FF69B4",  # Розовый
            "&H0032CD32",  # Зеленый
            "&H00FF4500"   # Оранжевый
        ]
        
        for i, word in enumerate(words):
            word_text = word['word'].strip()
            if not word_text:
                continue
                
            word_duration = (word['end'] - word['start']) * 100
            word_duration = max(10, int(word_duration))
            
            # Выбираем цвет для слова
            color = colors[i % len(colors)]
            
            # Создаем эффект с изменением цвета
            karaoke_parts.append(f"{{\\k{word_duration}\\c{color}}}{word_text}")
        
        return "".join(karaoke_parts)
    
    def generate_ass_subtitles(self, subtitle_data: Dict, output_path: str, 
                             style: str = "modern", custom_style: Optional[Dict] = None) -> bool:
        """Генерирует ASS файл с караоке-субтитрами"""
        try:
            # Подготавливаем стиль
            if custom_style:
                final_style = {**self.default_style, **custom_style}
            else:
                final_style = self.default_style.copy()
                
            # Настройки для разных стилей
            if style == "neon":
                final_style.update({
                    'primary_color': '&H00FFFF00',  # Циан
                    'secondary_color': '&H00FF00FF',  # Магента
                    'outline': 3,
                    'font_size': 22
                })
            elif style == "classic":
                final_style.update({
                    'primary_color': '&H00FFFFFF',  # Белый
                    'secondary_color': '&H000000FF',  # Красный
                    'outline': 2,
                    'font_size': 18
                })
            elif style == "minimal":
                final_style.update({
                    'outline': 1,
                    'shadow': 0,
                    'font_size': 16
                })
            
            # Создаем содержимое ASS файла
            content = self.create_ass_header(final_style)
            
            # Добавляем диалоги
            if 'segments' in subtitle_data:
                for segment in subtitle_data['segments']:
                    if style == "modern":
                        # Используем современный караоке-эффект
                        start_time = self.format_time(segment['start'])
                        end_time = self.format_time(segment['end'])
                        
                        if 'words' in segment and segment['words']:
                            karaoke_text = self.create_modern_karaoke_text(segment['words'], segment['start'])
                        else:
                            karaoke_text = segment['text'].strip()
                            
                        line = f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{karaoke_text}"
                        content += line + "\n"
                    else:
                        # Стандартный караоке-эффект
                        lines = self.create_karaoke_line(segment)
                        for line in lines:
                            content += line + "\n"
            
            # Сохраняем файл
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"✅ ASS субтитры сохранены: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации ASS субтитров: {e}")
            return False
    
    def generate_srt_subtitles(self, subtitle_data: Dict, output_path: str) -> bool:
        """Генерирует SRT файл для совместимости"""
        try:
            content = ""
            
            if 'segments' in subtitle_data:
                for i, segment in enumerate(subtitle_data['segments'], 1):
                    start_time = self.format_srt_time(segment['start'])
                    end_time = self.format_srt_time(segment['end'])
                    text = segment['text'].strip()
                    
                    content += f"{i}\n"
                    content += f"{start_time} --> {end_time}\n"
                    content += f"{text}\n\n"
            
            # Сохраняем файл
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"✅ SRT субтитры сохранены: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации SRT субтитров: {e}")
            return False
    
    def format_srt_time(self, seconds: float) -> str:
        """Конвертирует секунды в формат времени SRT (HH:MM:SS,mmm)"""
        td = timedelta(seconds=seconds)
        hours = int(td.total_seconds() // 3600)
        minutes = int((td.total_seconds() % 3600) // 60)
        secs = td.total_seconds() % 60
        milliseconds = int((secs % 1) * 1000)
        secs = int(secs)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
    
    def create_subtitle_styles(self) -> Dict[str, Dict]:
        """Возвращает предустановленные стили субтитров"""
        styles = {
            "modern": {
                "name": "Современный",
                "description": "Градиентные цвета с плавными переходами",
                "font_size": 20,
                "primary_color": "&H00FFFFFF",
                "secondary_color": "&H00FFD700"
            },
            "classic": {
                "name": "Классический",
                "description": "Традиционный караоке-стиль",
                "font_size": 18,
                "primary_color": "&H00FFFFFF",
                "secondary_color": "&H000000FF"
            },
            "neon": {
                "name": "Неоновый",
                "description": "Яркие неоновые цвета",
                "font_size": 22,
                "primary_color": "&H00FFFF00",
                "secondary_color": "&H00FF00FF"
            },
            "minimal": {
                "name": "Минимальный",
                "description": "Простой и чистый стиль",
                "font_size": 16,
                "primary_color": "&H00FFFFFF",
                "secondary_color": "&H00CCCCCC"
            },
            "opus_style": {
                "name": "Opus.pro",
                "description": "В стиле Opus.pro с радужными цветами",
                "font_size": 20,
                "primary_color": "&H00FFFFFF",
                "secondary_color": "&H00FF6B6B"
            }
        }
        
        return styles

# Функции для интеграции с основным приложением
def generate_karaoke_subtitles(subtitle_data: Dict, output_dir: str, 
                             video_id: str, style: str = "modern") -> Dict[str, str]:
    """Генерирует караоке-субтитры в разных форматах"""
    generator = KaraokeSubtitleGenerator()
    
    # Пути для файлов
    ass_path = os.path.join(output_dir, f"{video_id}_karaoke.ass")
    srt_path = os.path.join(output_dir, f"{video_id}_subtitles.srt")
    
    results = {}
    
    # Генерируем ASS файл
    if generator.generate_ass_subtitles(subtitle_data, ass_path, style):
        results['ass'] = ass_path
    
    # Генерируем SRT файл
    if generator.generate_srt_subtitles(subtitle_data, srt_path):
        results['srt'] = srt_path
    
    return results

def get_available_styles() -> Dict[str, Dict]:
    """Возвращает доступные стили субтитров"""
    generator = KaraokeSubtitleGenerator()
    return generator.create_subtitle_styles()

