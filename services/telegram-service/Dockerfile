FROM python:3.12-slim

# System packages: Tesseract + Turkish language pack
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-tur \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install platform packages first (for Docker layer caching)
COPY packages/platform-auth /app/packages/platform-auth
RUN pip install --no-cache-dir /app/packages/platform-auth

# Install service
COPY services/telegram-service/pyproject.toml /app/services/telegram-service/
COPY services/telegram-service/src /app/services/telegram-service/src
RUN pip install --no-cache-dir /app/services/telegram-service

WORKDIR /app/services/telegram-service

ENV PYTHONUNBUFFERED=1

EXPOSE 8106

CMD ["telegram-api"]
