# AgentFlow AI Clips v18.1.1

Профессиональная система генерации коротких клипов с ASS караоке-субтитрами.

## 🚀 Возможности

### 🎬 ASS Караоке Revolution
- ✅ **Переход от drawtext к ASS-формату** с караоке-эффектами
- ✅ **GPU-ускорение через libass** вместо CPU обработки
- ✅ **8-12 секунд** рендеринг vs 45-60 сек (в 5 раз быстрее!)
- ✅ **<1GB RAM** vs 2-3GB (в 3 раза меньше памяти)
- ✅ **Подсветка каждого слова** как в Opus.pro

### 🔧 Техническая архитектура
- ✅ **Двухэтапный процесс:** базовое видео + ASS субтитры
- ✅ **4 караоке-стиля:** Modern, Neon, Fire, Elegant
- ✅ **Умная группировка** слов в фразы (3-4 слова)
- ✅ **Автоматическая оптимизация** под нагрузку системы
- ✅ **Многоуровневая fallback система**

### 📊 Полная функциональность
- ✅ **Chunked транскрибация** для больших файлов
- ✅ **ChatGPT анализ** с JSON валидацией
- ✅ **4 формата обрезки:** 9:16, 16:9, 1:1, 4:5
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

## 🌐 Деплой на Render

### 1. Подключение GitHub репозитория

1. Войдите в [Render Dashboard](https://dashboard.render.com)
2. Нажмите **"New +"** → **"Web Service"**
3. Подключите GitHub репозиторий: `https://github.com/Serhooi/agentflow-ai-clips-v18`

### 2. Настройка сервиса

**Build & Deploy:**
- **Environment:** `Docker`
- **Build Command:** `docker build -t agentflow-ai-clips .`
- **Start Command:** `python app.py`

**Environment Variables:**
```
OPENAI_API_KEY=your-openai-api-key-here
SUPABASE_URL=https://vahgmyuowsilbxqdjjii.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key
PORT=8000
```

### 3. Advanced Settings

- **Instance Type:** `Starter` (или выше для production)
- **Auto-Deploy:** `Yes` (автоматический деплой при push)

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

### Минимальные
- **CPU:** 2 cores
- **RAM:** 2GB
- **Диск:** 5GB свободного места
- **FFmpeg** с поддержкой libass

### Рекомендуемые
- **CPU:** 4+ cores
- **RAM:** 4GB+
- **Диск:** 20GB+ SSD
- **GPU:** Для ускорения (опционально)

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

**AgentFlow AI Clips v18.1.1** - Профессиональная система генерации клипов с караоке-субтитрами! 🎬✨

