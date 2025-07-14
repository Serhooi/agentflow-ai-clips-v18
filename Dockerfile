# AgentFlow AI Clips v18.5.6 - Production Dockerfile
FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libass-dev \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Создание рабочей директории
WORKDIR /app

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения и Remotion директории
COPY . .

# Создание необходимых директорий
RUN mkdir -p uploads audio clips ass_subtitles remotion

# Установка Remotion зависимостей
RUN cd remotion && npm install @remotion/cli @remotion/renderer react react-dom

# Установка переменных окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Открытие порта
EXPOSE 8000

# Команда запуска
CMD ["python", "app.py"]
