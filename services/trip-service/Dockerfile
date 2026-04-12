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
COPY services/trip-service/ /build/services/trip-service/

RUN pip install uv
RUN uv pip install --no-cache --prefix=/install /build/packages/platform-auth \
    /build/packages/platform-common \
    /build/services/trip-service

# RUNTIME STAGE
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:${PATH}" \
    PYTHONPATH="/install/lib/python3.12/site-packages:${PYTHONPATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    ca-certificates \
    tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser
COPY --from=builder /install /install
COPY services/trip-service/alembic.ini ./alembic.ini
COPY services/trip-service/alembic ./alembic

USER appuser

EXPOSE 8101

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8101/health', timeout=3)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["trip-api"]