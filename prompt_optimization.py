#!/usr/bin/env python3
"""
Оптимизированные промпты для ускорения анализа ChatGPT
"""

def get_optimized_prompt(transcript_text: str, video_duration: float, content_type: str = "general") -> str:
    """Создает оптимизированный промпт для быстрого анализа"""
    
    # Определяем количество клипов
    if video_duration <= 60:
        target_clips = 1
    elif video_duration <= 180:
        target_clips = 2
    elif video_duration <= 600:
        target_clips = 3
    else:
        target_clips = 4
    
    # Сокращаем транскрипт если он слишком длинный
    max_transcript_length = 1500  # Меньше токенов = быстрее ответ
    if len(transcript_text) > max_transcript_length:
        # Берем начало, середину и конец
        part_size = max_transcript_length // 3
        transcript_text = (
            transcript_text[:part_size] + 
            " ... " + 
            transcript_text[len(transcript_text)//2 - part_size//2:len(transcript_text)//2 + part_size//2] + 
            " ... " + 
            transcript_text[-part_size:]
        )
    
    # Быстрые промпты для разных типов контента
    quick_prompts = {
        "educational": f"""Find {target_clips} best educational moments in this {video_duration:.0f}s video.
Look for: explanations, tips, how-to steps, key insights, examples.

Transcript: {transcript_text}

Return JSON: {{"highlights": [{{"start_time": 0, "end_time": 60, "title": "Key Tip", "description": "Why valuable"}}]}}
Each clip: 40-80 seconds, no overlap, times 0-{video_duration:.0f}.""",

        "entertainment": f"""Find {target_clips} funniest/most entertaining moments in this {video_duration:.0f}s video.
Look for: jokes, funny stories, surprising moments, emotional peaks.

Transcript: {transcript_text}

Return JSON: {{"highlights": [{{"start_time": 0, "end_time": 60, "title": "Funny Moment", "description": "Why entertaining"}}]}}
Each clip: 40-80 seconds, no overlap, times 0-{video_duration:.0f}.""",

        "business": f"""Find {target_clips} most valuable business insights in this {video_duration:.0f}s video.
Look for: strategies, results, advice, case studies, numbers.

Transcript: {transcript_text}

Return JSON: {{"highlights": [{{"start_time": 0, "end_time": 60, "title": "Business Tip", "description": "Why useful"}}]}}
Each clip: 40-80 seconds, no overlap, times 0-{video_duration:.0f}.""",

        "general": f"""Find {target_clips} best moments in this {video_duration:.0f}s video for short clips.
Look for: interesting insights, emotional moments, valuable information, entertaining parts.

Transcript: {transcript_text}

Return JSON: {{"highlights": [{{"start_time": 0, "end_time": 60, "title": "Best Moment", "description": "Why interesting"}}]}}
Each clip: 40-80 seconds, no overlap, times 0-{video_duration:.0f}."""
    }
    
    return quick_prompts.get(content_type, quick_prompts["general"])

def analyze_with_chatgpt_ultra_fast(transcript_text: str, video_duration: float) -> Optional[Dict]:
    """Ультра-быстрый анализ с минимальным промптом"""
    try:
        # Определяем тип контента быстро
        text_lower = transcript_text.lower()
        if any(word in text_lower for word in ['learn', 'teach', 'how to', 'explain']):
            content_type = "educational"
        elif any(word in text_lower for word in ['funny', 'joke', 'laugh', 'story']):
            content_type = "entertainment"
        elif any(word in text_lower for word in ['business', 'money', 'strategy', 'success']):
            content_type = "business"
        else:
            content_type = "general"
        
        prompt = get_optimized_prompt(transcript_text, video_duration, content_type)
        
        # Используем быструю модель с минимальными параметрами
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Самая быстрая модель
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,  # Минимум токенов
            temperature=0.1,  # Минимум креативности
            top_p=0.9  # Фокус на лучших вариантах
        )
        
        content = response.choices[0].message.content.strip()
        
        # Быстрая очистка JSON
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1]
        
        result = json.loads(content.strip())
        highlights = result.get("highlights", [])
        
        # Минимальная валидация
        for highlight in highlights:
            if highlight["end_time"] <= highlight["start_time"]:
                highlight["end_time"] = highlight["start_time"] + 50
            if highlight["end_time"] > video_duration:
                highlight["end_time"] = video_duration
        
        logger.info(f"⚡ Ультра-быстрый анализ: {len(highlights)} клипов за минимальное время")
        return {"highlights": highlights}
        
    except Exception as e:
        logger.error(f"Ошибка ультра-быстрого анализа: {e}")
        return None

def smart_content_detection(transcript_text: str) -> str:
    """Быстрое определение типа контента"""
    text_lower = transcript_text[:500].lower()  # Анализируем только начало
    
    keywords = {
        'educational': ['learn', 'teach', 'explain', 'understand', 'how to', 'tutorial', 'guide', 'lesson'],
        'entertainment': ['funny', 'hilarious', 'joke', 'laugh', 'story', 'amazing', 'crazy', 'wow'],
        'business': ['business', 'money', 'profit', 'strategy', 'success', 'entrepreneur', 'marketing'],
        'tech': ['technology', 'software', 'app', 'digital', 'ai', 'programming', 'code'],
        'personal': ['life', 'experience', 'personal', 'journey', 'story', 'advice', 'wisdom']
    }
    
    scores = {}
    for category, words in keywords.items():
        scores[category] = sum(1 for word in words if word in text_lower)
    
    return max(scores, key=scores.get) if max(scores.values()) > 0 else 'general'