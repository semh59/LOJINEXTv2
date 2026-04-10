FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY packages/platform-auth /app/packages/platform-auth
COPY packages/platform-common /app/packages/platform-common
COPY services/trip-service/pyproject.toml ./pyproject.toml
COPY services/trip-service/alembic.ini ./alembic.ini
COPY services/trip-service/alembic ./alembic
COPY services/trip-service/src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir /app/packages/platform-auth \
    && python -m pip install --no-cache-dir /app/packages/platform-common \
    && python -m pip install --no-cache-dir .

USER appuser

EXPOSE 8101

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8101/health', timeout=3)" || exit 1

CMD ["trip-api"]
