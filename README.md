# AgentFlow AI Clips v21.0.0

Оптимизированная система для создания коротких клипов с профессиональными субтитрами и караоке-эффектами.

## 🚀 Новые возможности

- **Whisper.cpp** - легкая и быстрая версия Whisper для транскрибации
- **Система очередей** - стабильная обработка видео без перезагрузок
- **Оптимизация памяти** - работает на серверах с 512MB RAM
- **ASS субтитры** - профессиональные караоке-эффекты
- **Burned-in видео** - видео с вшитыми субтитрами
- **Supabase интеграция** - хранение и доставка видео

## 📋 Требования

- Python 3.8+
- FFmpeg
- 512MB+ RAM
- Supabase аккаунт (опционально)
- OpenAI API ключ

## 🛠️ Установка

```bash
# Клонирование репозитория
git clone https://github.com/Serhooi/agentflow-ai-clips-v18.git
cd agentflow-ai-clips-v18

# Переключение на ветку с оптимизированной версией
git checkout whisper-cpp-queue

# Установка зависимостей
pip install -r requirements.txt

# Создание .env файла
cp .env.example .env
# Отредактируйте .env файл, добавив ваши ключи API
```

## 🚀 Запуск

```bash
# Локальный запуск
python app.py

# Или с uvicorn
uvicorn app:app --host 0.0.0.0 --port 10000
```

## 🌐 API Endpoints

### Загрузка видео

```
POST /api/videos/upload
```

Загружает видео и возвращает уникальный ID.

### Анализ видео

```
POST /api/videos/analyze
```

Ставит видео в очередь на анализ и транскрибацию.

### Проверка статуса

```
GET /api/videos/{video_id}/status
```

Возвращает текущий статус обработки видео:
- `queued` - в очереди на обработку
- `processing` - обрабатывается
- `completed` - обработка завершена
- `error` - ошибка обработки

### Получение транскрипта

```
GET /api/videos/{video_id}/transcript
```

Возвращает транскрипт видео с word-level таймингами.

### Получение выделенных моментов

```
GET /api/videos/{video_id}/highlights
```

Возвращает выделенные моменты для создания клипов.

### Получение ASS субтитров

```
GET /api/videos/{video_id}/subtitles/ass
```

Возвращает ASS субтитры с караоке-эффектами.

### Проверка здоровья

```
GET /health
```

Возвращает статус сервера и информацию о системе.

## 🔧 Настройка Supabase

1. Создайте проект на [Supabase](https://supabase.com/)
2. Создайте bucket `video-results` с публичным доступом:

```sql
INSERT INTO storage.buckets (id, name, public) 
VALUES ('video-results', 'video-results', true);
```

3. Добавьте переменные окружения:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-key
```

## 🚀 Деплой на Render.com

1. Подключите GitHub репозиторий к Render.com
2. Создайте новый Web Service
3. Настройте:
   - **Repository**: `https://github.com/Serhooi/agentflow-ai-clips-v18`
   - **Branch**: `whisper-cpp-queue`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py`
4. Добавьте переменные окружения:
   - `OPENAI_API_KEY`
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
5. Нажмите "Create Web Service"

## 📊 Производительность

- **RAM**: 512MB-1GB
- **Одновременная обработка**: 1 видео
- **Очередь**: Неограниченная
- **Время обработки**: ~1-2 минуты на видео (зависит от длительности)

## 🔍 Устранение неполадок

### Ошибка "Out of Memory"

Увеличьте лимит RAM на Render.com до 1GB или используйте еще более оптимизированную модель:

```python
whisper_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
```

### Ошибка с Supabase

Проверьте правильность ключей и URL. Если проблема сохраняется, используйте локальное хранение:

```
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
```

## 📝 Лицензия

MIT

