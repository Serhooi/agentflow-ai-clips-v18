#!/usr/bin/env python3
"""
Тест функции addEmojisToText
"""
import re
import random

def addEmojisToText(words, video_duration):
    """Добавляет эмоджи к тексту логично (2-4 на видео) в начале/конце предложений"""
    if not words:
        return words
    
    # Определяем количество эмоджи на основе длительности видео
    emoji_count = min(4, max(2, int(video_duration / 30)))  # 2-4 эмоджи в зависимости от длительности
    
    # Эмоджи для разных типов контента
    content_emojis = {
        'positive': ['😊', '👍', '✨', '🔥', '💪', '🎉', '👏', '💯', '🚀', '⭐'],
        'educational': ['🧠', '💡', '📚', '🎯', '🔍', '💭', '🤔', '📝', '🎓', '💻'],
        'exciting': ['🤩', '😍', '🔥', '⚡', '💥', '🎊', '🌟', '🎈', '🎁', '🏆'],
        'thoughtful': ['🤔', '💭', '🧐', '💡', '🎯', '📖', '✍️', '🔮', '🌱', '🔑']
    }
    
    # Объединяем все эмоджи для случайного выбора
    all_emojis = []
    for emoji_list in content_emojis.values():
        all_emojis.extend(emoji_list)
    
    # Находим границы предложений (слова, заканчивающиеся на . ! ?)
    sentence_boundaries = []
    for i, word in enumerate(words):
        word_text = word.get('word', '').strip()
        if re.search(r'[.!?]$', word_text) or i == len(words) - 1:
            sentence_boundaries.append(i)
    
    if not sentence_boundaries:
        # Если нет явных границ предложений, разделим по времени
        total_duration = words[-1].get('end', video_duration) if words else video_duration
        segment_duration = total_duration / emoji_count
        
        for i in range(emoji_count):
            target_time = (i + 1) * segment_duration
            # Найдём ближайшее слово к этому времени
            closest_idx = 0
            min_diff = float('inf')
            for j, word in enumerate(words):
                word_time = word.get('start', 0)
                diff = abs(word_time - target_time)
                if diff < min_diff:
                    min_diff = diff
                    closest_idx = j
            sentence_boundaries.append(closest_idx)
    
    # Ограничиваем количество границ
    if len(sentence_boundaries) > emoji_count:
        # Выбираем равномерно распределённые границы
        step = len(sentence_boundaries) // emoji_count
        sentence_boundaries = [sentence_boundaries[i * step] for i in range(emoji_count)]
    
    # Добавляем эмоджи к выбранным словам
    emojis_added = 0
    used_emojis = set()
    
    for boundary_idx in sentence_boundaries:
        if emojis_added >= emoji_count:
            break
            
        if boundary_idx < len(words):
            # Выбираем уникальный эмоджи
            available_emojis = [e for e in all_emojis if e not in used_emojis]
            if not available_emojis:
                available_emojis = all_emojis  # Если все использованы, начинаем заново
            
            emoji = random.choice(available_emojis)
            used_emojis.add(emoji)
            
            # Добавляем эмоджи в конец слова (после знаков препинания если есть)
            current_word = words[boundary_idx].get('word', '').strip()
            
            # Проверяем, есть ли уже эмоджи в слове
            if not re.search(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002600-\U000027BF\U0001f900-\U0001f9ff\U0001f018-\U0001f270]', current_word):
                words[boundary_idx]['word'] = current_word + ' ' + emoji
                emojis_added += 1
                print(f"🎭 Добавлен эмоджи '{emoji}' к слову '{current_word}' на позиции {boundary_idx}")
    
    print(f"🎭 Добавлено {emojis_added} эмоджи из {emoji_count} запланированных")
    return words

# Тестовые данные
test_words = [
    {'word': 'Hello', 'start': 0.0, 'end': 0.5},
    {'word': 'world', 'start': 0.5, 'end': 1.0},
    {'word': 'this', 'start': 1.0, 'end': 1.5},
    {'word': 'is', 'start': 1.5, 'end': 2.0},
    {'word': 'a', 'start': 2.0, 'end': 2.2},
    {'word': 'test.', 'start': 2.2, 'end': 2.8},
    {'word': 'Another', 'start': 3.0, 'end': 3.5},
    {'word': 'sentence', 'start': 3.5, 'end': 4.0},
    {'word': 'here!', 'start': 4.0, 'end': 4.5},
    {'word': 'And', 'start': 5.0, 'end': 5.2},
    {'word': 'final', 'start': 5.2, 'end': 5.6},
    {'word': 'words.', 'start': 5.6, 'end': 6.0}
]

import copy

print("=== Тест 1: Короткое видео (30 секунд) ===")
result1 = addEmojisToText(copy.deepcopy(test_words), 30.0)
print('Результат:')
for word in result1:
    print(f"  {word['word']} ({word['start']}-{word['end']})")

print("\n=== Тест 2: Длинное видео (120 секунд) ===")
result2 = addEmojisToText(copy.deepcopy(test_words), 120.0)
print('Результат:')
for word in result2:
    print(f"  {word['word']} ({word['start']}-{word['end']})")

print("\n=== Тест 3: Очень короткое видео (10 секунд) ===")
result3 = addEmojisToText(copy.deepcopy(test_words), 10.0)
print('Результат:')
for word in result3:
    print(f"  {word['word']} ({word['start']}-{word['end']})")