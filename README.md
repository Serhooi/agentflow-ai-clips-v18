# 🎬 AgentFlow AI Clips v19.0.0 - ShortGPT Integration

**Революционная система создания AI клипов с караоке-субтитрами на базе ShortGPT**

## 🚀 Ключевые особенности

### ✨ **ShortGPT Integration**
- **Проверенная архитектура** - основано на ShortGPT (6.6k ⭐)
- **Стабильная обработка видео** - надежные алгоритмы
- **Модульная система** - легко расширяемая

### 🎤 **Whisper AI Transcription**
- **Точная транскрибация** с временными метками
- **Поддержка множества языков**
- **Пословная синхронизация**

### 📝 **Караоке-субтитры ASS**
- **Подсветка слов** в реальном времени
- **4 стиля**: modern, neon, fire, elegant
- **Идеальная синхронизация** с речью

### 🎯 **Умный анализ контента**
- **Автоматический поиск** лучших моментов
- **Адаптивное количество клипов** (2-5 в зависимости от длительности)
- **Оптимальная длительность** каждого клипа

## 🛠️ Технологический стек

- **Backend**: FastAPI + Python 3.11
- **AI Engine**: ShortGPT Framework
- **Transcription**: Whisper-Timestamped
- **Video Processing**: FFmpeg + MoviePy
- **Subtitles**: ASS (Advanced SubStation Alpha)
- **Storage**: Supabase (опционально)

## 📋 API Endpoints

### 📤 **Загрузка видео**
```http
POST /api/videos/upload
Content-Type: multipart/form-data

file: video.mp4
```

### 🔍 **Анализ видео**
```http
POST /api/videos/analyze
Content-Type: application/json

{
  "video_id": "20241206_123456_video.mp4"
}
```

### 📊 **Статус анализа**
```http
GET /api/videos/{video_id}/status
```

### 🎬 **Генерация клипов**
```http
POST /api/clips/generate
Content-Type: application/json

{
  "video_id": "20241206_123456_video.mp4",
  "format_id": "9:16",
  "style_id": "modern",
  "num_clips": 3
}
```

### 📈 **Статус генерации**
```http
GET /api/clips/generation/{task_id}/status
```

### ⬇️ **Скачивание клипа**
```http
GET /api/clips/{clip_id}/download
```

## 🎨 Стили субтитров

### 🔥 **Modern** (по умолчанию)
- Белый текст с черной обводкой
- Зеленая подсветка караоке
- Шрифт: Arial, 24px

### 💫 **Neon**
- Циан текст
- Магента подсветка караоке
- Шрифт: Arial, 26px

### 🔥 **Fire**
- Желтый текст
- Оранжевая подсветка караоке
- Шрифт: Arial, 25px

### ✨ **Elegant**
- Белый текст
- Желтая подсветка караоке
- Шрифт: Times New Roman, 24px

## 📐 Форматы видео

- **9:16** - TikTok, Instagram Reels, YouTube Shorts (720x1280)
- **16:9** - YouTube, Facebook (1280x720)
- **1:1** - Instagram Posts (720x720)
- **4:5** - Instagram Stories (720x900)

## 🚀 Быстрый старт

### 1. Клонирование репозитория
```bash
git clone https://github.com/Serhooi/agentflow-shortgpt-v1.git
cd agentflow-shortgpt-v1
```

### 2. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 3. Настройка переменных окружения
```bash
export OPENAI_API_KEY="your_openai_api_key"
export SUPABASE_URL="your_supabase_url"  # опционально
export SUPABASE_ANON_KEY="your_supabase_anon_key"  # опционально
export SUPABASE_SERVICE_ROLE_KEY="your_supabase_service_key"  # опционально
```

### 4. Запуск приложения
```bash
python app.py
```

Приложение будет доступно по адресу: `http://localhost:8000`

## 🐳 Docker деплой

### Сборка образа
```bash
docker build -t agentflow-shortgpt .
```

### Запуск контейнера
```bash
docker run -p 8000:8000 \
  -e OPENAI_API_KEY="your_openai_api_key" \
  agentflow-shortgpt
```

## ☁️ Render деплой

1. **Подключите GitHub репозиторий** к Render
2. **Выберите тип сервиса**: Web Service
3. **Настройте переменные окружения**:
   - `OPENAI_API_KEY`
   - `SUPABASE_URL` (опционально)
   - `SUPABASE_ANON_KEY` (опционально)
   - `SUPABASE_SERVICE_ROLE_KEY` (опционально)

## 🔧 Конфигурация

### Основные настройки
```python
class Config:
    UPLOAD_DIR = "/tmp/agentflow_uploads"
    CLIPS_DIR = "/tmp/agentflow_clips"
    TEMP_DIR = "/tmp/agentflow_temp"
    
    # OpenAI API
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    # Supabase (опционально)
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
```

### Караоке-субтитры
```python
# Максимум 3 слова в фразе
max_words = 3

# Максимум 2.5 секунды на фразу
max_duration = 2.5

# Стили: modern, neon, fire, elegant
style = "modern"
```

## 📊 Производительность

- **Анализ видео**: ~30-60 секунд (зависит от длительности)
- **Генерация клипа**: ~15-30 секунд на клип
- **Поддерживаемые форматы**: MP4, AVI, MOV, MKV
- **Максимальный размер файла**: 500MB

## 🔍 Мониторинг

### Health Check
```http
GET /health
```

### Логи
```bash
tail -f agentflow_shortgpt.log
```

## 🤝 Интеграция с фронтендом

Этот API полностью совместим с существующим фронтендом AgentFlow. Просто измените базовый URL на новый сервис.

## 📈 Roadmap

- [ ] **Поддержка больше языков** для транскрибации
- [ ] **Кастомные стили субтитров** через API
- [ ] **Batch обработка** множественных видео
- [ ] **Webhook уведомления** о завершении обработки
- [ ] **Интеграция с YouTube API** для автоматической загрузки

## 🐛 Troubleshooting

### Проблема: FFmpeg не найден
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg
```

### Проблема: Ошибка Whisper
```bash
pip install --upgrade whisper-timestamped
```

### Проблема: Нет места на диске
```bash
# Очистка временных файлов
rm -rf /tmp/agentflow_*
```

## 📄 Лицензия

MIT License - см. файл LICENSE

## 🙏 Благодарности

- **ShortGPT** - за отличную архитектуру
- **OpenAI Whisper** - за точную транскрибацию
- **FFmpeg** - за мощную обработку видео

---

**Создано с ❤️ командой AgentFlow**

