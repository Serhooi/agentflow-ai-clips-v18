# AgentFlow AI Clips v19.1.0 - Правильная интеграция с ShortGPT
# Основано на оригинальном ShortGPT Dockerfile

FROM python:3.10-slim

# Устанавливаем системные зависимости (как в оригинальном ShortGPT)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install -r requirements.txt

# Клонируем ShortGPT
RUN git clone https://github.com/RayVentura/ShortGPT.git /app/ShortGPT

# Копируем код приложения
COPY . .

# Создаем необходимые директории
RUN mkdir -p /tmp/agentflow_uploads /tmp/agentflow_clips /tmp/agentflow_temp

# Открываем порт
EXPOSE 8000

# Запускаем приложение
CMD ["python", "app.py"]

