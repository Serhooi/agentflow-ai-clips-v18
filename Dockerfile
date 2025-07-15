# AgentFlow AI Clips v18.6.1 - Production Dockerfile
FROM python:3.11-slim

# Установка системных зависимостей включая Chrome зависимости для Remotion
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libass-dev \
    nodejs \
    npm \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    libu2f-udev \
    libvulkan1 \
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
