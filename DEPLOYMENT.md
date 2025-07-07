# 🚀 Deployment Instructions - AgentFlow AI Clips v20.1.2

## 📋 Быстрый деплой на Render.com

### 1️⃣ **Подготовка Environment Variables**

В Render.com Dashboard → Settings → Environment добавьте:

```bash
# ОБЯЗАТЕЛЬНО
OPENAI_API_KEY=sk-your-openai-key-here

# SUPABASE (для постоянного хранения видео)
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# ОПЦИОНАЛЬНО
PORT=10000
LOG_LEVEL=INFO
```

### 2️⃣ **Настройка Supabase Storage**

1. **Создайте проект в Supabase:**
   - Зайдите на https://supabase.com/dashboard
   - Создайте новый проект
   - Дождитесь завершения настройки

2. **Настройте Storage Bucket:**
   ```sql
   -- В SQL Editor выполните:
   
   -- Создание bucket
   INSERT INTO storage.buckets (id, name, public)
   VALUES ('video-results', 'video-results', true);
   
   -- Политика для публичного чтения
   CREATE POLICY "Public read access" ON storage.objects
   FOR SELECT USING (bucket_id = 'video-results');
   
   -- Политика для загрузки файлов
   CREATE POLICY "Service role upload" ON storage.objects
   FOR INSERT WITH CHECK (bucket_id = 'video-results');
   ```

3. **Получите ключи API:**
   - Settings → API
   - Скопируйте Project URL, anon key, service_role key

### 3️⃣ **Деплой на Render**

1. **Создайте Web Service:**
   - Repository: `https://github.com/Serhooi/agentflow-ai-clips-v18`
   - Branch: `whisperx-upgrade`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python app.py`

2. **Настройки сервиса:**
   - Environment: Python 3.11
   - Plan: Starter (512MB RAM)
   - Region: Выберите ближайший

3. **Environment Variables:**
   - Добавьте все переменные из шага 1

### 4️⃣ **Проверка деплоя**

После успешного деплоя проверьте:

```bash
# Health check
curl https://your-app.onrender.com/api/health

# Ожидаемый ответ:
{
  "status": "healthy",
  "version": "20.1.2",
  "features": {
    "whisperx": true,
    "supabase": true,
    "ass_subtitles": true,
    "burned_video": true
  }
}
```

## 🔧 Локальная разработка

### Установка:

```bash
# Клонирование
git clone https://github.com/Serhooi/agentflow-ai-clips-v18.git
cd agentflow-ai-clips-v18
git checkout whisperx-upgrade

# Установка зависимостей
pip install -r requirements.txt

# Настройка переменных окружения
cp .env.example .env
# Отредактируйте .env файл

# Запуск
python app.py
```

### Тестирование:

```bash
# Загрузка видео
curl -X POST "http://localhost:8000/api/videos/upload" \
  -F "file=@test_video.mp4"

# Проверка статуса
curl "http://localhost:8000/api/videos/{video_id}/status"

# Генерация ASS субтитров
curl -X POST "http://localhost:8000/api/subtitles/generate-ass" \
  -H "Content-Type: application/json" \
  -d '{"video_id": "your-id", "karaoke_mode": true}'
```

## 🐛 Устранение неполадок

### Ошибка "Supabase proxy argument"
```bash
# Обновите версию supabase
pip install supabase==2.7.4
```

### Ошибка "Out of Memory"
```bash
# В Environment Variables добавьте:
WHISPERX_MODEL=tiny
WHISPERX_BATCH_SIZE=4
```

### Ошибка "FFmpeg not found"
```bash
# Dockerfile уже включает FFmpeg
# Для локальной разработки:
sudo apt install ffmpeg  # Ubuntu
brew install ffmpeg      # macOS
```

### Проблемы с Supabase Storage
```bash
# Проверьте bucket существует:
curl -X GET "https://your-project.supabase.co/storage/v1/bucket/video-results" \
  -H "Authorization: Bearer your-service-role-key"

# Создайте bucket если нужно:
curl -X POST "https://your-project.supabase.co/storage/v1/bucket" \
  -H "Authorization: Bearer your-service-role-key" \
  -H "Content-Type: application/json" \
  -d '{"id": "video-results", "name": "video-results", "public": true}'
```

## 📊 Мониторинг

### Логи в Render:
- Dashboard → Logs
- Ищите сообщения: "✅ Supabase Storage подключен"

### Проверка памяти:
```bash
# В логах должно быть:
"🔄 Ленивая загрузка WhisperX модели..."
# А НЕ:
"🔄 Загрузка WhisperX модели..." (при старте)
```

### Тестирование API:
```bash
# Полный workflow
curl -X POST "http://your-app.onrender.com/api/videos/upload" \
  -F "file=@video.mp4" | jq '.video_id'

# Используйте полученный video_id для дальнейших запросов
```

## 🎯 Готовые команды для копирования

### Environment Variables для Render:
```
OPENAI_API_KEY=sk-your-key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-key
PORT=10000
LOG_LEVEL=INFO
```

### SQL для Supabase Storage:
```sql
INSERT INTO storage.buckets (id, name, public) VALUES ('video-results', 'video-results', true);
CREATE POLICY "Public read" ON storage.objects FOR SELECT USING (bucket_id = 'video-results');
CREATE POLICY "Service upload" ON storage.objects FOR INSERT WITH CHECK (bucket_id = 'video-results');
```

---

🎬 **AgentFlow AI Clips v20.1.2** готов к продакшену!

