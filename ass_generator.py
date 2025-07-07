# ass_generator.py - Генератор ASS субтитров с караоке-эффектами
# Создает .ass файлы в стиле Opus.pro для видеоплееров

import json
import re
from datetime import timedelta
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class ASSGenerator:
    """Генератор ASS субтитров с караоке-эффектами"""
    
    def __init__(self):
        self.default_style = {
            'font_name': 'Arial',
            'font_size': 20,
            'primary_color': '&H00FFFFFF',  # Белый
            'secondary_color': '&H000000FF',  # Красный
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
            'margin_v': 10,
            'encoding': 1
        }
        
        self.karaoke_style = {
            'font_name': 'Arial',
            'font_size': 22,
            'primary_color': '&H00FFD700',  # Золотой для подсветки
            'secondary_color': '&H00FFFFFF',  # Белый для обычного текста
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
            'outline': 3,
            'shadow': 2,
            'alignment': 2,  # Центр снизу
            'margin_l': 10,
            'margin_r': 10,
            'margin_v': 20,
            'encoding': 1
        }

    def format_time(self, seconds: float) -> str:
        """Конвертирует секунды в формат ASS времени (H:MM:SS.CC)"""
        td = timedelta(seconds=seconds)
        hours = int(td.total_seconds() // 3600)
        minutes = int((td.total_seconds() % 3600) // 60)
        secs = td.total_seconds() % 60
        centiseconds = int((secs % 1) * 100)
        secs = int(secs)
        
        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

    def create_style_line(self, name: str, style_dict: Dict[str, Any]) -> str:
        """Создает строку стиля для ASS файла"""
        return (
            f"Style: {name},"
            f"{style_dict['font_name']},"
            f"{style_dict['font_size']},"
            f"{style_dict['primary_color']},"
            f"{style_dict['secondary_color']},"
            f"{style_dict['outline_color']},"
            f"{style_dict['back_color']},"
            f"{-1 if style_dict['bold'] else 0},"
            f"{-1 if style_dict['italic'] else 0},"
            f"{-1 if style_dict['underline'] else 0},"
            f"{-1 if style_dict['strike_out'] else 0},"
            f"{style_dict['scale_x']},"
            f"{style_dict['scale_y']},"
            f"{style_dict['spacing']},"
            f"{style_dict['angle']},"
            f"{style_dict['border_style']},"
            f"{style_dict['outline']},"
            f"{style_dict['shadow']},"
            f"{style_dict['alignment']},"
            f"{style_dict['margin_l']},"
            f"{style_dict['margin_r']},"
            f"{style_dict['margin_v']},"
            f"{style_dict['encoding']}"
        )

    def create_karaoke_effect(self, words: List[Dict], segment_start: float) -> str:
        """Создает караоке-эффект для слов в сегменте"""
        if not words:
            return ""
        
        karaoke_tags = []
        current_time = 0
        
        for i, word in enumerate(words):
            word_start = word.get('start', segment_start)
            word_end = word.get('end', segment_start + 1)
            word_text = word.get('word', '').strip()
            
            if not word_text:
                continue
            
            # Время до начала слова (в сантисекундах)
            time_to_word = int((word_start - segment_start) * 100)
            
            # Длительность слова (в сантисекундах)
            word_duration = int((word_end - word_start) * 100)
            
            # Добавляем паузу до слова если нужно
            if time_to_word > current_time:
                pause_duration = time_to_word - current_time
                karaoke_tags.append(f"{{\\k{pause_duration}}}")
                current_time = time_to_word
            
            # Добавляем караоке-тег для слова
            karaoke_tags.append(f"{{\\k{word_duration}}}{word_text}")
            current_time += word_duration
            
            # Добавляем пробел между словами (кроме последнего)
            if i < len(words) - 1:
                karaoke_tags.append(" ")
        
        return "".join(karaoke_tags)

    def create_dialogue_line(self, start_time: float, end_time: float, 
                           text: str, style: str = "Default") -> str:
        """Создает строку диалога для ASS файла"""
        start_formatted = self.format_time(start_time)
        end_formatted = self.format_time(end_time)
        
        return (
            f"Dialogue: 0,"
            f"{start_formatted},"
            f"{end_formatted},"
            f"{style},,0,0,0,,"
            f"{text}"
        )

    def generate_ass_header(self, video_width: int = 1920, video_height: int = 1080) -> str:
        """Генерирует заголовок ASS файла"""
        header = [
            "[Script Info]",
            "Title: AgentFlow AI Clips - Karaoke Subtitles",
            "ScriptType: v4.00+",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: TV.709",
            f"PlayResX: {video_width}",
            f"PlayResY: {video_height}",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            self.create_style_line("Default", self.default_style),
            self.create_style_line("Karaoke", self.karaoke_style),
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
        ]
        
        return "\n".join(header)

    def generate_ass_from_whisperx(self, whisperx_data: Dict[str, Any], 
                                  output_path: str,
                                  karaoke_mode: bool = True,
                                  video_width: int = 1920,
                                  video_height: int = 1080) -> str:
        """
        Генерирует ASS файл из данных WhisperX
        
        Args:
            whisperx_data: Данные от WhisperX с сегментами и словами
            output_path: Путь для сохранения ASS файла
            karaoke_mode: Включить караоке-эффекты
            video_width: Ширина видео
            video_height: Высота видео
            
        Returns:
            Путь к созданному ASS файлу
        """
        try:
            # Создаем заголовок
            ass_content = [self.generate_ass_header(video_width, video_height)]
            
            # Обрабатываем сегменты
            segments = whisperx_data.get('segments', [])
            
            for segment in segments:
                start_time = segment.get('start', 0)
                end_time = segment.get('end', start_time + 1)
                text = segment.get('text', '').strip()
                words = segment.get('words', [])
                
                if not text:
                    continue
                
                if karaoke_mode and words:
                    # Создаем караоке-эффект
                    karaoke_text = self.create_karaoke_effect(words, start_time)
                    if karaoke_text:
                        dialogue_line = self.create_dialogue_line(
                            start_time, end_time, karaoke_text, "Karaoke"
                        )
                        ass_content.append(dialogue_line)
                else:
                    # Обычные субтитры без караоке
                    dialogue_line = self.create_dialogue_line(
                        start_time, end_time, text, "Default"
                    )
                    ass_content.append(dialogue_line)
            
            # Сохраняем файл
            final_content = "\n".join(ass_content)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            logger.info(f"ASS файл создан: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Ошибка создания ASS файла: {str(e)}")
            raise

    def generate_srt_from_whisperx(self, whisperx_data: Dict[str, Any], 
                                  output_path: str) -> str:
        """
        Генерирует SRT файл из данных WhisperX для совместимости
        
        Args:
            whisperx_data: Данные от WhisperX
            output_path: Путь для сохранения SRT файла
            
        Returns:
            Путь к созданному SRT файлу
        """
        try:
            srt_content = []
            segments = whisperx_data.get('segments', [])
            
            for i, segment in enumerate(segments, 1):
                start_time = segment.get('start', 0)
                end_time = segment.get('end', start_time + 1)
                text = segment.get('text', '').strip()
                
                if not text:
                    continue
                
                # Форматируем время для SRT (HH:MM:SS,mmm)
                start_srt = self.format_time_srt(start_time)
                end_srt = self.format_time_srt(end_time)
                
                srt_content.extend([
                    str(i),
                    f"{start_srt} --> {end_srt}",
                    text,
                    ""
                ])
            
            # Сохраняем файл
            final_content = "\n".join(srt_content)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            logger.info(f"SRT файл создан: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Ошибка создания SRT файла: {str(e)}")
            raise

    def format_time_srt(self, seconds: float) -> str:
        """Конвертирует секунды в формат SRT времени (HH:MM:SS,mmm)"""
        td = timedelta(seconds=seconds)
        hours = int(td.total_seconds() // 3600)
        minutes = int((td.total_seconds() % 3600) // 60)
        secs = td.total_seconds() % 60
        milliseconds = int((secs % 1) * 1000)
        secs = int(secs)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

    def create_advanced_karaoke_effects(self, words: List[Dict], 
                                      segment_start: float,
                                      effect_type: str = "highlight") -> str:
        """
        Создает продвинутые караоке-эффекты
        
        Args:
            words: Список слов с таймингами
            segment_start: Время начала сегмента
            effect_type: Тип эффекта (highlight, glow, wave, typewriter)
            
        Returns:
            Строка с ASS тегами для эффекта
        """
        if not words:
            return ""
        
        if effect_type == "highlight":
            return self.create_karaoke_effect(words, segment_start)
        
        elif effect_type == "glow":
            # Эффект свечения
            karaoke_tags = []
            for word in words:
                word_start = word.get('start', segment_start)
                word_duration = int((word.get('end', word_start + 1) - word_start) * 100)
                word_text = word.get('word', '').strip()
                
                if word_text:
                    # Добавляем эффект свечения
                    glow_effect = f"{{\\blur3\\bord3\\3c&H00FFD700&}}{{\\k{word_duration}}}{word_text}"
                    karaoke_tags.append(glow_effect)
            
            return "".join(karaoke_tags)
        
        elif effect_type == "wave":
            # Волновой эффект
            karaoke_tags = []
            for i, word in enumerate(words):
                word_start = word.get('start', segment_start)
                word_duration = int((word.get('end', word_start + 1) - word_start) * 100)
                word_text = word.get('word', '').strip()
                
                if word_text:
                    # Волновое движение
                    wave_offset = i * 5  # Смещение для волны
                    wave_effect = f"{{\\move(0,{wave_offset},0,0)}}{{\\k{word_duration}}}{word_text}"
                    karaoke_tags.append(wave_effect)
            
            return "".join(karaoke_tags)
        
        elif effect_type == "typewriter":
            # Эффект печатной машинки
            karaoke_tags = []
            for word in words:
                word_start = word.get('start', segment_start)
                word_duration = int((word.get('end', word_start + 1) - word_start) * 100)
                word_text = word.get('word', '').strip()
                
                if word_text:
                    # Эффект появления по буквам
                    typewriter_effect = f"{{\\fad(0,{word_duration//2})}}{{\\k{word_duration}}}{word_text}"
                    karaoke_tags.append(typewriter_effect)
            
            return "".join(karaoke_tags)
        
        else:
            # По умолчанию - обычный караоке
            return self.create_karaoke_effect(words, segment_start)

# Пример использования
if __name__ == "__main__":
    # Тестовые данные
    test_data = {
        "segments": [
            {
                "start": 0.0,
                "end": 3.5,
                "text": "Привет, это тестовые субтитры",
                "words": [
                    {"word": "Привет,", "start": 0.0, "end": 0.8},
                    {"word": "это", "start": 0.9, "end": 1.2},
                    {"word": "тестовые", "start": 1.3, "end": 2.1},
                    {"word": "субтитры", "start": 2.2, "end": 3.5}
                ]
            }
        ]
    }
    
    generator = ASSGenerator()
    
    # Создаем ASS файл с караоке
    ass_path = "/tmp/test_karaoke.ass"
    generator.generate_ass_from_whisperx(test_data, ass_path, karaoke_mode=True)
    
    # Создаем SRT файл для совместимости
    srt_path = "/tmp/test_subtitles.srt"
    generator.generate_srt_from_whisperx(test_data, srt_path)
    
    print(f"ASS файл создан: {ass_path}")
    print(f"SRT файл создан: {srt_path}")

