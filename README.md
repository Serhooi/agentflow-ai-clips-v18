# AgentFlow AI Clips v20.1.0 - WhisperX Upgrade

🎬 **Профессиональная система генерации коротких клипов с караоке-субтитрами как в Opus.pro**

## 🚀 Новые возможности v20.1.0

### ✨ **Революционные улучшения субтитров:**
- 🎯 **WhisperX интеграция** - word-level тайминги для каждого слова
- 🎤 **Караоке-эффекты** - подсветка слов в реальном времени
- 🎨 **ASS субтитры** - профессиональные субтитры с эффектами
- 🔥 **Burned-in видео** - видео с вшитыми субтитрами
- 📱 **React плеер** - интерактивные субтитры во фронтенде

### 🎯 **Качество как в Opus.pro:**
- ✅ Точная синхронизация слов с аудио
- ✅ Красивые караоке-эффекты
- ✅ Множество стилей субтитров
- ✅ Превью и предварительный просмотр
- ✅ Экспорт в разных форматах

## 📋 Содержание

- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
- [API Endpoints](#api-endpoints)
- [Компоненты React](#компоненты-react)
- [Стили субтитров](#стили-субтитров)
- [Деплой на Render](#деплой-на-render)
- [Примеры использования](#примеры-использования)

## 🛠 Установка

### Локальная установка

```bash
# Клонируем репозиторий
git clone https://github.com/your-repo/agentflow-whisperx-upgrade.git
cd agentflow-whisperx-upgrade

# Устанавливаем зависимости
pip install -r requirements.txt

# Устанавливаем FFmpeg (Ubuntu/Debian)
sudo apt update
sudo apt install ffmpeg

# Или на macOS
brew install ffmpeg

# Настраиваем переменные окружения
export OPENAI_API_KEY="your-openai-key"
export SUPABASE_URL="your-supabase-url"  # Опционально
export SUPABASE_ANON_KEY="your-key"      # Опционально

# Запускаем приложение
python app.py
```

### Docker установка

```bash
# Собираем образ
docker build -t agentflow-whisperx .

# Запускаем контейнер
docker run -p 8000:8000 \
  -e OPENAI_API_KEY="your-key" \
  agentflow-whisperx
```

## 🚀 Быстрый старт

### 1. Загрузка видео
```bash
curl -X POST "http://localhost:8000/api/videos/upload" \
  -F "file=@your_video.mp4"
```

### 2. Анализ видео (автоматически запускается)
```bash
curl "http://localhost:8000/api/videos/{video_id}/status"
```

### 3. Генерация ASS субтитров
```bash
curl -X POST "http://localhost:8000/api/subtitles/generate-ass" \
  -H "Content-Type: application/json" \
  -d '{
    "video_id": "your-video-id",
    "karaoke_mode": true,
    "style_name": "modern"
  }'
```

### 4. Создание видео с субтитрами
```bash
curl -X POST "http://localhost:8000/api/videos/burn-subtitles" \
  -H "Content-Type: application/json" \
  -d '{
    "video_id": "your-video-id",
    "quality": "high",
    "style_name": "modern"
  }'
```

## 📡 API Endpoints

### 🎬 Видео обработка
- `POST /api/videos/upload` - Загрузка видео
- `POST /api/videos/analyze` - Анализ видео с WhisperX
- `GET /api/videos/{video_id}/status` - Статус обработки

### 🎵 Субтитры
- `POST /api/subtitles/generate-ass` - Генерация ASS субтитров
- `GET /api/subtitles/download/{filename}` - Скачивание субтитров
- `GET /api/subtitles/styles` - Доступные стили
- `GET /api/subtitles/preview/{video_id}` - Превью субтитров

### 🔥 Burned-in видео
- `POST /api/videos/burn-subtitles` - Создание видео с субтитрами
- `POST /api/clips/burn-subtitles-batch` - Массовая обработка клипов
- `GET /api/videos/download-burned/{filename}` - Скачивание
- `GET /api/videos/burn-progress/{video_id}` - Прогресс создания

### ✂️ Генерация клипов
- `POST /api/clips/generate` - Генерация клипов
- `GET /api/clips/generation/{task_id}/status` - Статус генерации
- `GET /api/clips/download/{filename}` - Скачивание клипов

## ⚛️ Компоненты React

### SubtitlePlayer - Караоке плеер

```tsx
import { SubtitlePlayer, useSubtitlePlayer } from './SubtitlePlayer';

function VideoPlayer() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const { isPlaying, currentTime, togglePlay } = useSubtitlePlayer(videoRef);
  
  return (
    <div className="video-container">
      <video ref={videoRef} src="your-video.mp4" />
      
      <SubtitlePlayer
        videoRef={videoRef}
        subtitleData={subtitleData}
        style="modern"
        position="bottom"
        fontSize="medium"
        highlightColor="#FFD700"
      />
      
      <button onClick={togglePlay}>
        {isPlaying ? 'Pause' : 'Play'}
      </button>
    </div>
  );
}
```

### Настройки SubtitlePlayer

```tsx
interface SubtitlePlayerProps {
  videoRef: React.RefObject<HTMLVideoElement>;
  subtitleData: SubtitleData | null;
  style?: 'modern' | 'classic' | 'neon' | 'minimal';
  position?: 'bottom' | 'top' | 'center';
  fontSize?: 'small' | 'medium' | 'large';
  showBackground?: boolean;
  highlightColor?: string;
  textColor?: string;
}
```

## 🎨 Стили субтитров

### Modern (по умолчанию)
- Шрифт: Montserrat
- Цвет: Белый текст, зеленая подсветка
- Эффект: Градиентная подсветка

### Neon
- Шрифт: Arial
- Цвет: Белый текст, пурпурная подсветка
- Эффект: Неоновое свечение

### Fire
- Шрифт: Impact
- Цвет: Белый текст, оранжевая подсветка
- Эффект: Огненные цвета

### Получение доступных стилей
```bash
curl "http://localhost:8000/api/subtitles/styles"
```

## 🌐 Деплой на Render

### 1. Подготовка репозитория
```bash
# Коммитим все изменения
git add .
git commit -m "v20.1.0: WhisperX + ASS + Burned-in видео"
git push origin main
```

### 2. Настройка Render.com
1. Создайте новый Web Service
2. Подключите GitHub репозиторий
3. Настройте переменные окружения:
   - `OPENAI_API_KEY` - ваш ключ OpenAI
   - `SUPABASE_URL` - URL Supabase (опционально)
   - `SUPABASE_ANON_KEY` - ключ Supabase (опционально)

### 3. Настройки деплоя
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python app.py`
- **Environment:** Python 3.11
- **Region:** Выберите ближайший

### 4. Проверка деплоя
```bash
curl "https://your-app.onrender.com/api/health"
```

## 📖 Примеры использования

### Полный workflow обработки видео

```python
import requests
import time

# 1. Загружаем видео
with open('video.mp4', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/api/videos/upload',
        files={'file': f}
    )
video_id = response.json()['video_id']

# 2. Ждем завершения анализа
while True:
    status = requests.get(f'http://localhost:8000/api/videos/{video_id}/status')
    if status.json()['status'] == 'completed':
        break
    time.sleep(5)

# 3. Генерируем ASS субтитры
requests.post('http://localhost:8000/api/subtitles/generate-ass', json={
    'video_id': video_id,
    'karaoke_mode': True,
    'style_name': 'modern'
})

# 4. Создаем видео с субтитрами
requests.post('http://localhost:8000/api/videos/burn-subtitles', json={
    'video_id': video_id,
    'quality': 'high',
    'style_name': 'modern'
})

# 5. Скачиваем результат
burned_video = requests.get(f'http://localhost:8000/api/videos/download-burned/{video_id}_burned_high.mp4')
with open('result.mp4', 'wb') as f:
    f.write(burned_video.content)
```

### Интеграция с React фронтендом

```tsx
// Загрузка и обработка видео
const uploadVideo = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await fetch('/api/videos/upload', {
    method: 'POST',
    body: formData
  });
  
  const { video_id } = await response.json();
  return video_id;
};

// Генерация субтитров
const generateSubtitles = async (videoId: string, style: string) => {
  const response = await fetch('/api/subtitles/generate-ass', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      video_id: videoId,
      karaoke_mode: true,
      style_name: style
    })
  });
  
  return response.json();
};

// Создание burned-in видео
const burnSubtitles = async (videoId: string, quality: string) => {
  const response = await fetch('/api/videos/burn-subtitles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      video_id: videoId,
      quality: quality,
      style_name: 'modern'
    })
  });
  
  return response.json();
};
```

## 🔧 Конфигурация

### Настройки качества видео
- **low** - 500k битрейт, быстрое кодирование
- **medium** - 1000k битрейт, среднее качество
- **high** - 2000k битрейт, высокое качество (рекомендуется)
- **ultra** - 4000k битрейт, максимальное качество

### Настройки WhisperX
```python
# В app.py можно настроить:
WHISPERX_MODEL = "large-v2"  # Модель Whisper
WHISPERX_DEVICE = "cpu"      # Устройство (cpu/cuda)
WHISPERX_BATCH_SIZE = 16     # Размер батча
```

## 🐛 Устранение неполадок

### Ошибка "FFmpeg не найден"
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# CentOS/RHEL
sudo yum install ffmpeg

# macOS
brew install ffmpeg
```

### Ошибка "CUDA не доступна"
```bash
# Для CPU-only режима добавьте в переменные окружения:
export WHISPERX_DEVICE="cpu"
```

### Проблемы с памятью
```bash
# Уменьшите размер батча WhisperX:
export WHISPERX_BATCH_SIZE=8
```

## 📊 Производительность

### Время обработки (примерно):
- **Анализ видео (5 мин):** ~2-3 минуты
- **Генерация ASS:** ~5-10 секунд
- **Burned-in видео:** ~1-2 минуты
- **Генерация клипов:** ~30-60 секунд

### Требования к ресурсам:
- **RAM:** Минимум 2GB, рекомендуется 4GB
- **CPU:** 2+ ядра
- **Диск:** 1GB свободного места на видео
- **GPU:** Опционально для ускорения

## 🔄 Обновления

### v20.1.0 (текущая)
- ✅ WhisperX интеграция
- ✅ ASS субтитры с караоке
- ✅ Burned-in видео с FFmpeg
- ✅ React караоке-плеер
- ✅ Множественные стили

### v18.3.0 (предыдущая)
- ✅ Базовая генерация клипов
- ✅ Простые субтитры
- ✅ OpenAI интеграция

## 🤝 Поддержка

### Документация API
Полная документация доступна по адресу: `http://localhost:8000/docs`

### Логи и отладка
```bash
# Включить подробные логи
export LOG_LEVEL=DEBUG
python app.py
```

### Контакты
- GitHub Issues: [Создать issue](https://github.com/your-repo/issues)
- Email: support@agentflow.ai

## 📄 Лицензия

MIT License - см. файл [LICENSE](LICENSE)

---

🎬 **AgentFlow AI Clips v20.1.0** - Профессиональные короткие клипы с караоке-субтитрами как в Opus.pro!

