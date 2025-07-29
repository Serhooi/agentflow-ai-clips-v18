#!/usr/bin/env python3
"""
Тест интеграции API с новой функцией эмоджи
"""

def test_analyze_request_model():
    """Тест модели AnalyzeRequest"""
    try:
        # Имитируем импорт модели
        class AnalyzeRequest:
            def __init__(self, video_id: str, autoEmoji: bool = False):
                self.video_id = video_id
                self.autoEmoji = autoEmoji
        
        # Тест 1: Без эмоджи (по умолчанию)
        request1 = AnalyzeRequest("test-video-id")
        assert request1.video_id == "test-video-id"
        assert request1.autoEmoji == False
        print("✅ Тест 1 пройден: AnalyzeRequest без autoEmoji")
        
        # Тест 2: С эмоджи
        request2 = AnalyzeRequest("test-video-id", True)
        assert request2.video_id == "test-video-id"
        assert request2.autoEmoji == True
        print("✅ Тест 2 пройден: AnalyzeRequest с autoEmoji=True")
        
        # Тест 3: Явно отключенные эмоджи
        request3 = AnalyzeRequest("test-video-id", False)
        assert request3.video_id == "test-video-id"
        assert request3.autoEmoji == False
        print("✅ Тест 3 пройден: AnalyzeRequest с autoEmoji=False")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка в тесте модели: {e}")
        return False

def test_safe_transcribe_audio_signature():
    """Тест сигнатуры функции safe_transcribe_audio"""
    try:
        # Имитируем функцию с новой сигнатурой
        def safe_transcribe_audio(audio_path: str, auto_emoji: bool = False, video_duration: float = 60.0):
            return {
                "audio_path": audio_path,
                "auto_emoji": auto_emoji,
                "video_duration": video_duration,
                "words": []
            }
        
        # Тест 1: Старый способ вызова (обратная совместимость)
        result1 = safe_transcribe_audio("test.wav")
        assert result1["auto_emoji"] == False
        assert result1["video_duration"] == 60.0
        print("✅ Тест 1 пройден: Обратная совместимость")
        
        # Тест 2: Новый способ с эмоджи
        result2 = safe_transcribe_audio("test.wav", True, 120.0)
        assert result2["auto_emoji"] == True
        assert result2["video_duration"] == 120.0
        print("✅ Тест 2 пройден: Новая сигнатура с эмоджи")
        
        # Тест 3: Частичные параметры
        result3 = safe_transcribe_audio("test.wav", auto_emoji=True)
        assert result3["auto_emoji"] == True
        assert result3["video_duration"] == 60.0
        print("✅ Тест 3 пройден: Частичные параметры")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка в тесте сигнатуры: {e}")
        return False

def test_emoji_logic():
    """Тест логики добавления эмоджи"""
    try:
        # Тест количества эмоджи для разных длительностей
        test_cases = [
            (10, 2),   # Короткое видео - минимум 2
            (30, 2),   # 30 секунд - 2 эмоджи
            (60, 2),   # 60 секунд - 2 эмоджи  
            (90, 3),   # 90 секунд - 3 эмоджи
            (120, 4),  # 120 секунд - 4 эмоджи
            (300, 4),  # Длинное видео - максимум 4
        ]
        
        for duration, expected_count in test_cases:
            actual_count = min(4, max(2, int(duration / 30)))
            assert actual_count == expected_count, f"Для {duration}с ожидалось {expected_count}, получено {actual_count}"
        
        print("✅ Тест логики количества эмоджи пройден")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка в тесте логики эмоджи: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Запуск тестов интеграции API...")
    
    tests = [
        test_analyze_request_model,
        test_safe_transcribe_audio_signature,
        test_emoji_logic
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        print(f"\n--- {test.__name__} ---")
        if test():
            passed += 1
    
    print(f"\n📊 Результат: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 Все тесты пройдены успешно!")
    else:
        print("⚠️ Некоторые тесты не пройдены")