# AgentFlow AI Clips v18.6.0

Профессиональная система генерации коротких клипов с субтитрами.

## 🚀 Возможности

### 🎬 Основная функциональность
- ✅ **Автоматическая нарезка видео** на хайлайты
- ✅ **Whisper транскрипция** с word-level таймингами
- ✅ **ChatGPT анализ** для поиска интересных моментов
- ✅ **Субтитры с синхронизацией** по словам
- ✅ **4 стиля субтитров:** Modern, Neon, Fire, Elegant

### 🔧 Техническая архитектура
- ✅ **FastAPI backend** с асинхронной обработкой
- ✅ **FFmpeg интеграция** для обработки видео
- ✅ **4 формата обрезки:** 9:16, 16:9, 1:1, 4:5
- ✅ **Умная группировка** слов в субтитры
- ✅ **Fallback система** при ошибках
- ✅ **Supabase Storage** (опционально)

### 📊 Дополнительные возможности
- ✅ **Chunked транскрибация** для больших файлов
- ✅ **JSON валидация** результатов
- ✅ **Real-time мониторинг** прогресса
- ✅ **Автоматическая очистка** старых файлов

## 🛠️ Установка и запуск

### Локальная разработка

```bash
# Клонирование репозитория
git clone https://github.com/Serhooi/agentflow-ai-clips-v18.git
cd agentflow-ai-clips-v18

# Установка зависимостей
pip install -r requirements.txt

# Установка системных зависимостей (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install ffmpeg libass-dev

# Настройка переменных окружения
export OPENAI_API_KEY="your-openai-api-key"

# Запуск
python app.py
```

### Docker

```bash
# Сборка образа
docker build -t agentflow-ai-clips .

# Запуск контейнера
docker run -p 8000:8000 -e OPENAI_API_KEY="your-key" agentflow-ai-clips
```

## 🌐 Деплой на Render.com

### Быстрый деплой (1 клик)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

### Ручной деплой

#### 1. Подключение GitHub репозитория

1. Войдите в [Render Dashboard](https://dashboard.render.com)
2. Нажмите **"New +"** → **"Web Service"**
3. Подключите этот GitHub репозиторий

#### 2. Настройка сервиса

**Build & Deploy:**
- **Environment:** `Python 3`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python app.py`

**Environment Variables:**
```
OPENAI_API_KEY=your-openai-api-key-here
PORT=8000
```

**Опционально (для масштабирования):**
```
REDIS_URL=redis://your-redis-url:6379
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

#### 3. Advanced Settings

- **Instance Type:** `Starter` (512MB RAM, $7/месяц)
- **Auto-Deploy:** `Yes` (автоматический деплой при push в GitHub)

### Масштабирование до 100+ пользователей

#### Добавление Redis (опционально)
1. **New** → **Redis** → **Starter** ($7/месяц)
2. Скопировать `REDIS_URL` в переменные Web Service
3. Система автоматически переключится на очередь задач

#### Добавление Background Workers (для высокой нагрузки)
1. **New** → **Background Worker**
2. **Build Command:** `pip install -r requirements.txt`
3. **Start Command:** `python worker.py`
4. **Environment Variables:** те же + `WORKER_ID=worker-1`

**Результат:** 1 воркер = +20-30 пользователей

## 📡 API Документация

### Основные endpoints

#### 1. Загрузка видео
```http
POST /api/videos/upload
Content-Type: multipart/form-data

file: video.mp4
```

**Ответ:**
```json
{
  "video_id": "uuid",
  "filename": "video.mp4",
  "duration": 60.5,
  "size": 15728640,
  "status": "uploaded"
}
```

#### 2. Анализ видео
```http
POST /api/videos/analyze
Content-Type: application/json

{
  "video_id": "uuid"
}
```

#### 3. Статус анализа
```http
GET /api/videos/{video_id}/status
```

**Ответ:**
```json
{
  "video_id": "uuid",
  "status": "completed",
  "highlights": [
    {
      "start_time": 0,
      "end_time": 20,
      "title": "Заголовок клипа",
      "description": "Описание",
      "keywords": ["ключевые", "слова"]
    }
  ]
}
```

#### 4. Генерация клипов
```http
POST /api/clips/generate
Content-Type: application/json

{
  "video_id": "uuid",
  "format_id": "9:16",
  "style_id": "modern"
}
```

#### 5. Статус генерации
```http
GET /api/clips/generation/{task_id}/status
```

**Ответ:**
```json
{
  "task_id": "uuid",
  "status": "completed",
  "progress": 100,
  "current_stage": "completed",
  "clips": [
    {
      "id": "clip_1",
      "title": "Клип 1",
      "download_url": "/api/clips/download/clip_1.mp4",
      "duration": 20,
      "words_count": 45
    }
  ]
}
```

#### 6. Скачивание клипа
```http
GET /api/clips/download/{filename}
```

### Вспомогательные endpoints

#### Форматы
```http
GET /api/formats
```

#### Стили
```http
GET /api/styles
```

#### Статистика системы
```http
GET /api/stats
```

#### Health check
```http
GET /health
```

## 🎨 Доступные стили субтитров

### Modern
- **Шрифт:** Montserrat
- **Цвета:** Белый текст + зеленая подсветка
- **Эффекты:** Тонкая обводка

### Neon
- **Шрифт:** Arial
- **Цвета:** Белый текст + розовая подсветка
- **Эффекты:** Яркая обводка

### Fire
- **Шрифт:** Impact
- **Цвета:** Белый текст + оранжевая подсветка
- **Эффекты:** Тень + обводка

### Elegant
- **Шрифт:** Georgia
- **Цвета:** Белый текст + желтая подсветка
- **Эффекты:** Курсив + тень

## 📱 Поддерживаемые форматы

- **9:16** - Вертикальный (Instagram Stories, TikTok)
- **16:9** - Горизонтальный (YouTube, Facebook)
- **1:1** - Квадратный (Instagram Posts)
- **4:5** - Портретный (Instagram Feed)

## 🔧 Системные требования

### Минимальные (оптимизировано для 512MB RAM)
- **CPU:** 1 core
- **RAM:** 512MB (оптимизировано!)
- **Диск:** 2GB свободного места
- **FFmpeg** с поддержкой libass

### Рекомендуемые
- **CPU:** 2+ cores
- **RAM:** 1GB+
- **Диск:** 10GB+ SSD

### Оптимизации для 512MB RAM
- **Максимальный размер файла:** 100MB (вместо 500MB)
- **Максимум одновременных задач:** 2
- **Автоочистка:** каждые 10 минут
- **Лимит памяти процесса:** 400MB
- **Оптимизированные FFmpeg команды** с минимальным потреблением памяти

## 🐛 Troubleshooting

### Ошибки транскрибации
```
timestamp_granularities not supported
```
**Решение:** Обновите OpenAI API до последней версии или используйте fallback режим.

### Ошибки кодировки
```
UnicodeDecodeError
```
**Решение:** Все файловые операции используют UTF-8 с обработкой ошибок.

### Высокая нагрузка
```
CPU/RAM usage > 80%
```
**Решение:** Система автоматически оптимизирует обработку при высокой нагрузке.

## 📈 Мониторинг

Система включает встроенный мониторинг:
- **CPU/RAM usage** - каждую минуту
- **Автоочистка** старых файлов - каждый час
- **Health checks** - доступны через `/health`

## 🔐 Безопасность

- **CORS** настроен для всех доменов (настройте для production)
- **Лимиты размера** файлов (500MB)
- **Автоочистка** временных файлов
- **Валидация** входных данных

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи сервиса
2. Убедитесь что все зависимости установлены
3. Проверьте переменные окружения
4. Обратитесь к разработчику

---

**AgentFlow AI Clips v18.6.0** - Профессиональная система генерации клипов с субтитрами! 🎬✨

