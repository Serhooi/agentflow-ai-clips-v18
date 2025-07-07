# AgentFlow AI Clips v20.0.0 - По рекомендациям ChatGPT
# Основано на официальном Dockerfile ShortGPT

# Используем официальную версию Python как в ShortGPT
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

# Устанавливаем зависимости (БЕЗ кэша для избежания проблем)
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Клонируем ShortGPT (как в официальной инструкции)
RUN git clone https://github.com/RayVentura/ShortGPT.git /app/ShortGPT

# Копируем код нашего приложения
COPY . .

# Создаем необходимые директории для временных файлов
RUN mkdir -p /tmp/agentflow_uploads /tmp/agentflow_clips /tmp/agentflow_temp

# Открываем порт для FastAPI
EXPOSE 8000

# Запускаем наше приложение
CMD ["python", "app.py"]

