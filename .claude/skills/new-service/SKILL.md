---
name: new-service
description: Scaffold a new LOJINEXTv2 microservice. Use when the user asks to create a new service, bootstrap a service skeleton, or set up a new domain service. Triggers include "create new service", "scaffold service", "bootstrap <name>-service".
allowed-tools: Bash, Write, Edit, Read
---

# New Service Scaffold

## Pre-flight

1. Read `MEMORY/PLATFORM_STANDARD.md` — confirm the service name, port, and database name are registered in §1.
2. If not registered, stop and ask the user to add the entry to `PLATFORM_STANDARD.md` first.
3. Check `MEMORY/DECISIONS.md` for any relevant ADRs.

## Directory Structure

Create under `services/<service-name>/`:

```
services/<service-name>/
├── src/
│   └── <service_name>/
│       ├── __init__.py
│       ├── main.py               # FastAPI app factory
│       ├── config.py             # pydantic-settings BaseSettings
│       ├── database.py           # async engine + session factory
│       ├── models/
│       │   └── __init__.py
│       ├── schemas/
│       │   └── __init__.py
│       ├── routers/
│       │   └── __init__.py
│       ├── services/
│       │   └── __init__.py
│       └── repositories/
│           └── __init__.py
├── tests/
│   ├── conftest.py               # testcontainers setup
│   └── __init__.py
├── alembic/
│   ├── env.py
│   └── versions/
├── alembic.ini
├── pyproject.toml
├── Dockerfile
└── .env.example
```

## Required Endpoints

Every service MUST expose:
- `GET /health` — liveness (returns `{"status": "ok"}`)
- `GET /ready` — readiness (checks DB connectivity)
- `GET /metrics` — Prometheus metrics

## main.py Template

```python
from fastapi import FastAPI
from .routers import health

def create_app() -> FastAPI:
    app = FastAPI(title="<service-name>")
    app.include_router(health.router)
    return app

app = create_app()
```

## config.py Template

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    service_name: str = "<service-name>"

settings = Settings()
```

## conftest.py Template

```python
import pytest
from httpx import AsyncClient, ASGITransport
from testcontainers.postgres import PostgresContainer
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

@pytest.fixture(scope="session")
def postgres():
    with PostgresContainer("postgres:16") as pg:
        yield pg

@pytest.fixture
async def session(postgres):
    engine = create_async_engine(postgres.get_connection_url().replace("postgresql", "postgresql+asyncpg"))
    async with engine.begin() as conn:
        # run alembic migrations here
        pass
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as s:
        yield s
    await engine.dispose()
```

## After Scaffolding

1. Register service in `MEMORY/PLATFORM_STANDARD.md` §1 (if not already).
2. Update `MEMORY/PROJECT_STATE.md` with the new task status.
3. Verify `GET /health` returns 200 before declaring done.
