# BUILDER STAGE
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY packages/platform-auth /build/packages/platform-auth
COPY packages/platform-common /build/packages/platform-common
COPY services/telegram-service/ /build/services/telegram-service/

RUN pip install uv
RUN uv pip install --no-cache --prefix=/install /build/packages/platform-auth \
    /build/packages/platform-common \
    /build/services/telegram-service

# RUNTIME STAGE
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:${PATH}" \
    PYTHONPATH="/install/lib/python3.12/site-packages:${PYTHONPATH}"

# System packages: Tesseract + Turkish language pack + tini
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-tur \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    tzdata \
    ca-certificates \
    tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser
COPY --from=builder /install /install

USER appuser

EXPOSE 8106

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8106/health', timeout=3)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["telegram-api"]
