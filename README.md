# AgentFlow AI Clips v20.1.0 - WhisperX Upgrade

Улучшенная версия с WhisperX для получения word-level таймингов субтитров.

## 🚀 Новые возможности

### WhisperX интеграция
- **Word-level тайминги** - точные временные метки для каждого слова
- **Улучшенное выравнивание** текста с аудио
- **Fallback на OpenAI** Whisper API при недоступности WhisperX
- **CPU оптимизация** для Render.com

### Улучшенные субтитры
- Более точная синхронизация слов с видео
- Лучшее качество караоке-эффекта
- Поддержка русского языка по умолчанию

## 📋 Изменения от v18.3.0

### Добавлено
- `whisperx` библиотека для транскрибации
- `torch` и `torchaudio` для WhisperX
- Функция `init_whisperx()` для инициализации моделей
- Улучшенная функция `safe_transcribe_audio()` с WhisperX

### Изменено
- Версия API: `18.1.7` → `20.1.0`
- Описание: добавлено "с улучшенными субтитрами WhisperX"
- Транскрибация: приоритет WhisperX, fallback на OpenAI

## 🛠 Установка

```bash
pip install -r requirements.txt
```

## 🔧 Переменные окружения

```env
OPENAI_API_KEY=your_openai_key
SUPABASE_URL=your_supabase_url (опционально)
SUPABASE_ANON_KEY=your_anon_key (опционально)
SUPABASE_SERVICE_ROLE_KEY=your_service_key (опционально)
```

## 🚀 Запуск

```bash
python app.py
```

## 📊 Статус компонентов

API endpoint `/health` показывает статус:
- `whisperx`: доступность WhisperX
- `supabase`: подключение к Supabase
- `openai`: OpenAI API

## 🔄 Fallback логика

1. **Приоритет**: WhisperX для локальной обработки
2. **Fallback**: OpenAI Whisper API при ошибках
3. **Результат**: Единый формат с word-level таймингами

## 📈 Производительность

- **WhisperX**: Быстрее на CPU, лучшее качество
- **Память**: Модели кэшируются глобально
- **Оптимизация**: `int8` compute type для CPU

