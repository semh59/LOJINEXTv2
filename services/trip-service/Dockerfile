# ── Stage 1: Build ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY packages/platform-auth /build/packages/platform-auth
COPY packages/platform-common /build/packages/platform-common
COPY services/trip-service/pyproject.toml ./pyproject.toml
COPY services/trip-service/src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir /build/packages/platform-auth \
    && python -m pip install --no-cache-dir /build/packages/platform-common \
    && python -m pip install --no-cache-dir . \
    && python -m pip list --format=freeze > /build/requirements.txt

# ── Stage 2: Production (distroless) ────────────────────────────
FROM python:3.12-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY services/trip-service/alembic.ini ./alembic.ini
COPY services/trip-service/alembic ./alembic
COPY services/trip-service/src ./src

USER appuser

EXPOSE 8101

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8101/health', timeout=3)" || exit 1

CMD ["trip-api"]