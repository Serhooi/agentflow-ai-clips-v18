# Модуль субтитров на основе ShortGPT
# Простое и надежное решение без тяжелых зависимостей

import re
import logging

logger = logging.getLogger(__name__)

def getCaptionsWithTime(transcriptions, maxCaptionSize=15, considerPunctuation=True):
    """
    Создает субтитры с таймингами на основе транскрипции
    Скопировано из ShortGPT - проверенное решение
    """
    time_splits = []
    current_caption = []
    current_length = 0
    
    # Работаем только с сегментами которые имеют word-level тайминги
    segments = [seg for seg in transcriptions.get('segments', []) if 'words' in seg]
    
    # Собираем все слова из всех сегментов
    all_words = []
    for segment in segments:
        all_words.extend(segment['words'])
    
    for i, word in enumerate(all_words):
        word_text = word.get('text', '').strip()
        if not word_text:
            continue
        
        # Проверяем превысит ли это слово maxCaptionSize
        new_length = current_length + len(word_text) + (1 if current_caption else 0)
        
        # Определяем нужно ли разделить здесь
        should_split = (
            new_length > maxCaptionSize or
            (considerPunctuation and word_text.rstrip('.,!?') != word_text and current_caption) or
            i == len(all_words) - 1 or
            len(current_caption) >= 5
        )
        
        # Добавляем слово к текущему субтитру если еще не разделяем
        if not should_split:
            current_caption.append(word_text)
            current_length = new_length
            continue
            
        # Обрабатываем разделение
        if current_caption:
            # Добавляем текущее слово если это последнее
            if i == len(all_words) - 1 and new_length <= maxCaptionSize:
                current_caption.append(word_text)
                
            caption_text = ' '.join(current_caption)
            start_time = all_words[i - len(current_caption)]['start']
            end_time = word['end'] if word_text in current_caption else all_words[i - 1]['end']
            time_splits.append(((start_time, end_time), caption_text))
            
        # Обрабатываем текущее слово если оно не было добавлено к предыдущему субтитру
        if word_text not in current_caption and i == len(all_words) - 1:
            time_splits.append(((word['start'], word['end']), word_text))
            
        # Сбрасываем для следующего субтитра
        current_caption = []
        current_length = 0
        
        # Начинаем новый субтитр с текущим словом если это не последнее
        if i < len(all_words) - 1:
            current_caption.append(word_text)
            current_length = len(word_text)
    
    return time_splits

def create_simple_subtitle_filter(segments, style='modern'):
    """
    Создает простой FFmpeg фильтр для субтитров на основе подхода ShortGPT
    Без сложных караоке-эффектов, просто надежные субтитры
    """
    if not segments:
        logger.warning("📝 Нет сегментов для субтитров")
        return ""
    
    logger.info(f"📝 Создаем простые субтитры для {len(segments)} сегментов")
    
    # Простой стиль как в ShortGPT
    fontsize = 24
    fontcolor = 'white'
    bordercolor = 'black'
    borderw = 2
    
    # Создаем простые drawtext фильтры
    drawtext_filters = []
    
    for i, segment in enumerate(segments):
        start_time = segment.get('start', 0)
        end_time = segment.get('end', 0)
        text = segment.get('text', '').strip()
        
        if not text or end_time <= start_time:
            continue
        
        # Очищаем текст (как в ShortGPT)
        text = re.sub(r'[^\w\s\-_"\'\']', '', text)
        
        # Ограничиваем длину
        if len(text) > 50:
            text = text[:47] + "..."
        
        if not text:
            continue
        
        # Простой drawtext фильтр (стиль ShortGPT)
        drawtext = f"drawtext=text='{text}':fontsize={fontsize}:fontcolor={fontcolor}:bordercolor={bordercolor}:borderw={borderw}:x=(w-text_w)/2:y=h-text_h-60:enable='between(t,{start_time},{end_time})'"
        
        drawtext_filters.append(drawtext)
        logger.info(f"📝 Субтитр {i+1}: '{text}' ({start_time:.1f}s - {end_time:.1f}s)")
    
    if not drawtext_filters:
        logger.warning("📝 Не удалось создать ни одного фильтра субтитров")
        return ""
    
    result = ",".join(drawtext_filters)
    logger.info(f"✅ Создан простой фильтр субтитров: {len(drawtext_filters)} сегментов")
    return result

def create_word_level_subtitles(transcript_data, max_caption_size=15):
    """
    Создает субтитры с word-level таймингами используя подход ShortGPT
    """
    if not transcript_data or 'segments' not in transcript_data:
        logger.warning("📝 Нет данных транскрипции для субтитров")
        return []
    
    # Используем функцию из ShortGPT
    captions_with_time = getCaptionsWithTime(transcript_data, max_caption_size)
    
    # Конвертируем в наш формат
    subtitles = []
    for (start_time, end_time), text in captions_with_time:
        subtitles.append({
            'start': start_time,
            'end': end_time,
            'text': text.strip()
        })
    
    logger.info(f"✅ Создано {len(subtitles)} субтитров с word-level таймингами")
    return subtitles

