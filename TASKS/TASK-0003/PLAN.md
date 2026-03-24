# TASK-0003 PLAN — Location Service: Scaffold, Schema & Foundation

## Objective

A deployable `services/location-service/` project exists with all 15 database tables, full constraints, and core foundation modules. The service starts, /health returns 200, and migration runs cleanly.

## How I Understand the Problem

This is the first task in a multi-task Location Service build. It establishes the project structure, database schema, and shared utilities that all subsequent tasks depend on. No business endpoints beyond health/ready. No domain logic. Just the solid foundation.

## Approach

1. Create `services/location-service/` directory structure
2. Create `pyproject.toml` with dependencies (matching Trip Service + Pillow, canonicaljson)
3. Create `alembic.ini` and `alembic/env.py`
4. Implement `src/location_service/__init__.py`
5. Implement `config.py` — all env vars from Section 13 via pydantic-settings
6. Implement `database.py` — async engine + session factory
7. Implement `enums.py` — 17 enum classes covering all domain statuses
8. Implement `errors.py` — ProblemDetailError + ~40 error factories from each Section 7 error code
9. Implement `middleware.py` — RequestId (pure ASGI), ETag/row_version, cursor pagination, idempotency key
10. Implement `models.py` — all 15 SQLAlchemy models with CHECK constraints, partial unique indexes, FKs
11. Create Alembic migration `001_initial_schema.py`
12. Implement `observability.py` — structured JSON logging with mandatory fields
13. Implement `routers/health.py` — /health (liveness) and /ready (DB + config)
14. Implement `main.py` — FastAPI app, lifespan, middleware, health router
15. Write `conftest.py` with testcontainers PostgreSQL fixture
16. Write migration verification test
17. Verify `ruff` and `mypy` pass

## Files That Will Change

All new files:

```
services/location-service/pyproject.toml
services/location-service/alembic.ini
services/location-service/alembic/env.py
services/location-service/alembic/script.py.mako
services/location-service/alembic/versions/001_initial_schema.py
services/location-service/src/location_service/__init__.py
services/location-service/src/location_service/config.py
services/location-service/src/location_service/database.py
services/location-service/src/location_service/enums.py
services/location-service/src/location_service/errors.py
services/location-service/src/location_service/main.py
services/location-service/src/location_service/middleware.py
services/location-service/src/location_service/models.py
services/location-service/src/location_service/observability.py
services/location-service/src/location_service/schemas.py
services/location-service/src/location_service/routers/__init__.py
services/location-service/src/location_service/routers/health.py
services/location-service/tests/__init__.py
services/location-service/tests/conftest.py
services/location-service/tests/test_schema.py
```

Existing files updated:

```
MEMORY/PROJECT_STATE.md
TASKS/TASK-0003/STATE.md
TASKS/TASK-0003/CHANGED_FILES.md
TASKS/TASK-0003/TEST_EVIDENCE.md
TASKS/TASK-0003/NEXT_AGENT.md
```

## Risks

1. **15-table schema complexity** — Many cross-table CHECK constraints and partial unique indexes. Must verify all constraints work together.
2. **row_version trigger** — PostgreSQL BEFORE UPDATE trigger for auto-increment. Must be part of migration, not just model.
3. **JSONB columns** — route_versions has 5 JSONB columns; need to confirm SQLAlchemy/asyncpg handles them correctly.

## Test Cases

- test_migration_creates_all_15_tables — run migration, verify all tables exist
- test_migration_constraints — insert violating data, verify constraints reject
- test_health_returns_200 — GET /health → 200
- test_ready_returns_correct_status — GET /ready → checks DB connectivity

## Out of Scope

- Domain logic (normalization, codes, classification, hashing) → TASK-0004
- Point & Pair CRUD endpoints → TASK-0005
- Provider adapters & processing pipeline → TASK-0006
- Approval, delete, bulk refresh → TASK-0007
- Import/export, internal endpoints → TASK-0008
- Full test suite (Section 22) → TASK-0009

## Completion Criterion

- [ ] All 15 tables created with correct columns, constraints, indexes
- [ ] Alembic migration runs cleanly against PostgreSQL
- [ ] /health returns 200
- [ ] /ready checks DB connectivity
- [ ] ruff + mypy pass
- [ ] Migration verification test passes
