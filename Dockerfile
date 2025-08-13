# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Базовые настройки Python и дефолтный порт (Back4App передаст свой в $PORT)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Ставим зависимости отдельно — чтобы кешировалось
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Копируем приложение
COPY . /app

# Сообщаем платформе, что внутри слушаем этот порт
EXPOSE 8000

# Запуск Uvicorn; важно слушать $PORT, который задаёт платформа
CMD ["sh","-c","uvicorn api.index:app --host 0.0.0.0 --port ${PORT}"]
