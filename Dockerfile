# AgentFlow AI Clips v19.0.2 - ShortGPT Integration (Cache Bypass)
FROM python:3.11-slim

# Устанавливаем системные зависимости
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
# Принудительный сброс кэша для tinymongo v19.0.4
RUN pip install --no-cache-dir -r requirements.txt

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

