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
COPY services/identity-service/ /build/services/identity-service/

RUN pip install uv
RUN uv pip install --no-cache --prefix=/install /build/packages/platform-auth \
    /build/packages/platform-common \
    /build/services/identity-service

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
COPY services/identity-service/alembic.ini ./alembic.ini
COPY services/identity-service/alembic ./alembic

USER appuser

EXPOSE 8105

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c 'import urllib.request; urllib.request.urlopen("http://localhost:8105/ready")' || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["identity-api"]
