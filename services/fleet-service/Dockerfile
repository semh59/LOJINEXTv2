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
COPY services/fleet-service/pyproject.toml ./pyproject.toml
COPY services/fleet-service/src ./src
COPY services/fleet-service/alembic ./alembic
COPY services/fleet-service/alembic.ini ./alembic.ini

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir /app/packages/platform-auth \
    && python -m pip install --no-cache-dir /app/packages/platform-common \
    && python -m pip install --no-cache-dir .

USER appuser

CMD ["fleet-api"]
