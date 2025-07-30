#!/usr/bin/env python3
"""
Система контроля качества для оптимизаций
"""
import os
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class QualityController:
    """Контроллер качества для анализа видео"""
    
    def __init__(self):
        self.quality_metrics = {
            "audio_quality": "good",
            "analysis_quality": "good", 
            "processing_speed": "normal"
        }
    
    def check_audio_quality(self, audio_path: str, original_video_path: str) -> Dict:
        """Проверяет качество извлеченного аудио"""
        try:
            # Проверяем размер аудио файла
            audio_size = os.path.getsize(audio_path)
            video_size = os.path.getsize(original_video_path)
            
            # Аудио должно быть 1-5% от размера видео
            audio_ratio = audio_size / video_size
            
            quality_assessment = {
                "audio_size_mb": audio_size / (1024 * 1024),
                "video_size_mb": video_size / (1024 * 1024),
                "audio_ratio": audio_ratio,
                "quality": "good"
            }
            
            # Проверяем качество
            if audio_ratio < 0.005:  # Меньше 0.5%
                quality_assessment["quality"] = "low"
                quality_assessment["warning"] = "Аудио файл слишком маленький, возможна потеря качества"
            elif audio_ratio > 0.1:  # Больше 10%
                quality_assessment["quality"] = "inefficient"
                quality_assessment["warning"] = "Аудио файл слишком большой, можно сжать больше"
            
            logger.info(f"🎵 Качество аудио: {quality_assessment['quality']}, размер: {quality_assessment['audio_size_mb']:.1f}MB")
            return quality_assessment
            
        except Exception as e:
            logger.error(f"Ошибка проверки качества аудио: {e}")
            return {"quality": "unknown", "error": str(e)}
    
    def validate_analysis_quality(self, analysis_result: Dict, transcript_text: str, video_duration: float) -> Dict:
        """Проверяет качество анализа ChatGPT"""
        try:
            highlights = analysis_result.get("highlights", [])
            
            quality_metrics = {
                "clips_count": len(highlights),
                "total_coverage": 0,
                "avg_clip_duration": 0,
                "title_quality": 0,
                "description_quality": 0,
                "time_validity": 0,
                "overall_quality": "good"
            }
            
            if not highlights:
                quality_metrics["overall_quality"] = "failed"
                quality_metrics["error"] = "Нет найденных клипов"
                return quality_metrics
            
            # Проверяем покрытие видео
            total_clip_duration = sum(h["end_time"] - h["start_time"] for h in highlights)
            quality_metrics["total_coverage"] = total_clip_duration / video_duration
            quality_metrics["avg_clip_duration"] = total_clip_duration / len(highlights)
            
            # Проверяем качество заголовков
            valid_titles = 0
            for highlight in highlights:
                title = highlight.get("title", "")
                if title and len(title.split()) >= 2 and len(title.split()) <= 6:
                    valid_titles += 1
            quality_metrics["title_quality"] = valid_titles / len(highlights)
            
            # Проверяем качество описаний
            valid_descriptions = 0
            for highlight in highlights:
                description = highlight.get("description", "")
                if description and len(description) > 10:
                    valid_descriptions += 1
            quality_metrics["description_quality"] = valid_descriptions / len(highlights)
            
            # Проверяем валидность времени
            valid_times = 0
            for highlight in highlights:
                start = highlight.get("start_time", 0)
                end = highlight.get("end_time", 0)
                if 0 <= start < end <= video_duration and (end - start) >= 30:
                    valid_times += 1
            quality_metrics["time_validity"] = valid_times / len(highlights)
            
            # Общая оценка качества
            overall_score = (
                quality_metrics["title_quality"] * 0.3 +
                quality_metrics["description_quality"] * 0.3 +
                quality_metrics["time_validity"] * 0.4
            )
            
            if overall_score >= 0.8:
                quality_metrics["overall_quality"] = "excellent"
            elif overall_score >= 0.6:
                quality_metrics["overall_quality"] = "good"
            elif overall_score >= 0.4:
                quality_metrics["overall_quality"] = "acceptable"
            else:
                quality_metrics["overall_quality"] = "poor"
            
            logger.info(f"📊 Качество анализа: {quality_metrics['overall_quality']}, покрытие: {quality_metrics['total_coverage']:.1%}")
            return quality_metrics
            
        except Exception as e:
            logger.error(f"Ошибка валидации качества анализа: {e}")
            return {"overall_quality": "error", "error": str(e)}
    
    def should_use_fast_mode(self, video_duration: float, transcript_length: int) -> bool:
        """Определяет, стоит ли использовать быстрый режим"""
        
        # Факторы для принятия решения
        factors = {
            "short_video": video_duration <= 180,  # Короткое видео
            "simple_content": transcript_length <= 1000,  # Простой контент
            "fast_mode_enabled": os.getenv("FAST_MODE", "false").lower() == "true",
            "high_load": False  # TODO: проверить нагрузку системы
        }
        
        # Логика принятия решения
        if factors["fast_mode_enabled"]:
            if factors["short_video"] and factors["simple_content"]:
                logger.info("⚡ Быстрый режим: короткое видео + простой контент")
                return True
            elif factors["short_video"]:
                logger.info("⚡ Быстрый режим: короткое видео")
                return True
            elif factors["high_load"]:
                logger.info("⚡ Быстрый режим: высокая нагрузка системы")
                return True
        
        logger.info("🎯 Полный режим: приоритет качества")
        return False
    
    def get_quality_report(self, video_id: str, processing_time: float, quality_metrics: Dict) -> Dict:
        """Создает отчет о качестве обработки"""
        
        report = {
            "video_id": video_id,
            "processing_time": processing_time,
            "quality_metrics": quality_metrics,
            "recommendations": [],
            "overall_rating": "good"
        }
        
        # Анализируем результаты и даем рекомендации
        if quality_metrics.get("audio_quality", {}).get("quality") == "low":
            report["recommendations"].append("Увеличить битрейт аудио для лучшего качества")
        
        if quality_metrics.get("analysis_quality", {}).get("overall_quality") == "poor":
            report["recommendations"].append("Использовать полный режим анализа вместо быстрого")
        
        if processing_time > 120:  # Больше 2 минут
            report["recommendations"].append("Рассмотреть включение быстрого режима")
        
        # Общий рейтинг
        audio_good = quality_metrics.get("audio_quality", {}).get("quality") in ["good", "excellent"]
        analysis_good = quality_metrics.get("analysis_quality", {}).get("overall_quality") in ["good", "excellent"]
        speed_good = processing_time <= 90
        
        if audio_good and analysis_good and speed_good:
            report["overall_rating"] = "excellent"
        elif audio_good and analysis_good:
            report["overall_rating"] = "good"
        elif audio_good or analysis_good:
            report["overall_rating"] = "acceptable"
        else:
            report["overall_rating"] = "poor"
        
        return report

# Глобальный контроллер качества
quality_controller = QualityController()

def enhanced_analyze_video_task(task_id: str, video_id: str, auto_emoji: bool = False):
    """Анализ видео с контролем качества"""
    import time
    start_time = time.time()
    
    try:
        logger.info(f"🔍 Начат анализ с контролем качества: {video_id}")
        
        # ... основная логика анализа ...
        
        # В конце добавляем проверку качества
        processing_time = time.time() - start_time
        
        # Собираем метрики качества
        quality_metrics = {
            "audio_quality": quality_controller.check_audio_quality(audio_path, video_path),
            "analysis_quality": quality_controller.validate_analysis_quality(analysis_result, transcript_text, video_duration)
        }
        
        # Создаем отчет
        quality_report = quality_controller.get_quality_report(video_id, processing_time, quality_metrics)
        
        logger.info(f"📊 Отчет качества: {quality_report['overall_rating']}, время: {processing_time:.1f}s")
        
        # Добавляем отчет к результату
        analysis_tasks[task_id]["quality_report"] = quality_report
        
    except Exception as e:
        logger.error(f"Ошибка анализа с контролем качества: {e}")
        raise