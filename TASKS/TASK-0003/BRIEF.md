# TASK-0003 BRIEF — Location Service: Scaffold, Schema & Foundation

## Purpose

Create the `services/location-service/` project scaffold, implement all 15 database tables with full constraints, and deliver core foundation modules (config, errors, enums, middleware, database).

## What Must Exist After This Task

- `services/location-service/` project with pyproject.toml, alembic, src layout
- `config.py` with all 30+ env vars from spec Section 13
- `database.py` with async SQLAlchemy engine
- `enums.py` with all 17 domain enum classes
- `errors.py` with ProblemDetailError + ~40 error factories
- `middleware.py` with RequestId, ETag, cursor pagination, idempotency helpers
- `main.py` FastAPI entry point (no routers yet)
- `models.py` with all 15 SQLAlchemy table models
- Alembic migration creating all tables, constraints, partial unique indexes
- `observability.py` with structured logging setup
- `routers/health.py` with /health and /ready endpoints
- Migration verified against PostgreSQL via testcontainers

## Source of Truth

`LOCATION_SERVICE_PLAN_FINAL_v0_7_AUDITED.md` (v0.7) — Sections 1–4, 13–14, 3A.

## Technology Stack

Same as Trip Service: Python 3.12+ / FastAPI / SQLAlchemy 2.0 async / asyncpg / Alembic / PostgreSQL 16.
Port: 8103. Env prefix: `LOCATION_`.

## Out of Scope

- All API endpoints except /health and /ready
- Domain logic (normalization, codes, classification, hashing)
- Provider adapters
- Processing pipeline
- Tests beyond migration verification
