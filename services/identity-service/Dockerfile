FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY packages/platform-auth /app/packages/platform-auth
COPY services/identity-service/pyproject.toml ./pyproject.toml
COPY services/identity-service/alembic.ini ./alembic.ini
COPY services/identity-service/alembic ./alembic
COPY services/identity-service/src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir /app/packages/platform-auth \
    && python -m pip install --no-cache-dir .

USER appuser

EXPOSE 8105

CMD ["identity-api"]
