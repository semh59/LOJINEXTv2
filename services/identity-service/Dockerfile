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
COPY services/identity-service/pyproject.toml ./pyproject.toml
COPY services/identity-service/alembic.ini ./alembic.ini
COPY services/identity-service/alembic ./alembic
COPY services/identity-service/src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir /app/packages/platform-auth \
    && python -m pip install --no-cache-dir /app/packages/platform-common \
    && python -m pip install --no-cache-dir .

USER appuser

EXPOSE 8105

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8105/health')" || exit 1

CMD ["identity-api"]
