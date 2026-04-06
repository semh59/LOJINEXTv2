# CLAUDE.md — LOJINEXTv2

> User instructions always override this file.
> `MEMORY/PLATFORM_STANDARD.md` is binding on all service work — read it before touching any service.

---

## Approach

- Think before acting. Read existing files before writing code.
- Prefer editing over rewriting whole files.
- Do not re-read files you have already read unless the file may have changed.
- Be concise in output but thorough in reasoning.
- Test your code before declaring done.
- Keep solutions simple and direct.
- No sycophantic openers or closing fluff.

---

## Project Overview

LOJINEXTv2 is a microservices logistics platform. All backend code, comments, commit messages, and documentation MUST be in English.

| Service           | Port | Database          | Domain                          |
|-------------------|------|-------------------|---------------------------------|
| identity-service  | 8105 | identity_service  | Auth, users, JWT keys           |
| trip-service      | 8101 | trip_service      | Trip lifecycle                  |
| location-service  | 8103 | location_service  | Routes, location authority      |
| driver-service    | 8104 | driver_service    | Driver master data              |
| fleet-service     | 8102 | fleet_service     | Vehicles, trailers              |

---

## Technology Stack

```
Runtime         : Python 3.12+
Framework       : FastAPI (async ASGI)
ORM             : SQLAlchemy 2.0 (async)
DB Driver       : asyncpg
Migrations      : Alembic (one independent chain per service)
Database        : PostgreSQL 16+
ID Generation   : ULID via python-ulid (26-character string)
Async HTTP      : httpx.AsyncClient
Validation      : Pydantic v2 + pydantic-settings
Broker Client   : confluent-kafka
Shared Auth     : packages/platform-auth
Shared Utils    : packages/platform-common
Testing         : pytest + pytest-asyncio (asyncio_mode=auto)
Test DB         : testcontainers[postgres]
```

---

## Boundaries (Hard Rules)

- A service MUST NOT connect to another service's database.
- A service MUST NOT import Python modules from another service's package.
- Cross-domain data is exchanged exclusively via HTTP or Kafka events.
- ADR-001 locked: Trip calls Fleet for reference validation. Fleet calls Driver internally. Trip MUST NOT call Driver directly.

---

## Memory & Tracking Files

Before starting any task, check relevant files:

| File                          | Purpose                                      |
|-------------------------------|----------------------------------------------|
| `MEMORY/PLATFORM_STANDARD.md` | Binding engineering standard — read first   |
| `MEMORY/PROJECT_STATE.md`     | Current task status and next task ID        |
| `MEMORY/DECISIONS.md`         | Architectural decisions log (ADRs)          |
| `MEMORY/KNOWN_ISSUES.md`      | Known drift and open defects                |
| `TASKS/`                      | Per-task spec files                         |

---

## Code Conventions

- Use ULID (26-char string) for all entity IDs — never UUID.
- All timestamps use `datetime` with UTC timezone.
- Pydantic v2 models: use `model_config = ConfigDict(...)` not class `Config`.
- SQLAlchemy 2.0 style only — no legacy 1.x patterns.
- All DB operations must be async (`async with session` pattern).
- Use `platform-auth` package for JWT validation — never re-implement auth logic.
- Error responses must conform to the platform error format (see `PLATFORM_STANDARD.md` §6).

---

## API Design

- All routes versioned under `/v1/`.
- Route names: plural nouns, kebab-case (e.g., `/v1/trip-assignments`).
- Pagination: cursor-based for lists, always return `next_cursor` + `items`.
- Health: `GET /health` → liveness. `GET /ready` → readiness (checks DB + deps).
- Metrics: `GET /metrics` → Prometheus format.

---

## Testing

- Integration tests hit a real PostgreSQL via testcontainers — no DB mocks.
- Unit tests for pure business logic only.
- Every new endpoint needs at least: happy path + 422 validation + auth failure tests.
- Run tests per-service: `cd services/<name> && pytest`.

---

## Git & Task Workflow

- Task IDs follow `TASK-XXXX` format. Current next ID is in `MEMORY/PROJECT_STATE.md`.
- Commit messages: short imperative, reference task ID when applicable (e.g., `feat(trip): add backfill gate TASK-0046`).
- Update `MEMORY/PROJECT_STATE.md` task status when completing or changing task state.
- Do NOT push to remote without explicit user instruction.

---

## Token Efficiency

- Do not repeat information already established in the conversation.
- Avoid restating the task before starting — just do it.
- Skip summaries of what you just did; the diff is visible.
- For multi-step work, use TodoWrite to track progress, not prose narration.
- Prefer targeted file reads (offset/limit) over reading entire large files.

---

## What NOT To Do

- Do not add docstrings, comments, or type annotations to code you didn't change.
- Do not add features, refactors, or "improvements" beyond what was asked.
- Do not add error handling for scenarios that can't happen — trust internal guarantees.
- Do not create helpers or abstractions for one-time operations.
- Do not use backwards-compat shims for dead code — delete it cleanly.
- Do not make breaking changes to the platform error response format without a `DECISIONS.md` entry.
