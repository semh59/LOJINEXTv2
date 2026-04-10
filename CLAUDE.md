# CLAUDE.md — LOJINEXTv2

> User instructions always override this file.

---

## Before Starting Any Task

Read these files in order. No exceptions.

1. **`standards/PLATFORM_STANDARD.md`** — Binding engineering standard. Read in full.
2. **`standards/SERVICE_REGISTRY.md`** — Service identities, ports, call boundaries.
3. **`standards/DECISIONS.md`** — Locked architectural decisions. Do not re-make them.
4. **`standards/KNOWN_ISSUES.md`** — Known drift and open defects. Do not re-report.
5. **`TASKS/`** — Check for existing task history before starting new work.
6. **`MEMORY/PROJECT_STATE.md`** — Current task status and next task ID.

---

## Approach

- Think before acting. Read existing files before writing code.
- Prefer editing over rewriting whole files.
- Test your code before declaring done.
- Keep solutions simple and direct.
- No sycophantic openers or closing fluff.
- Do not re-read files you have already read unless they may have changed.

---

## Code Conventions (Quick Reference)

See `standards/PLATFORM_STANDARD.md` for the complete and binding rules.
The summary below is for quick reference only — the standard takes precedence.

**General:**
- All code, comments, commits in English.
- ULID for all entity IDs (26-char string). Never UUID.
- UTC timestamps with `_utc` suffix. `datetime.utcnow()` is forbidden.
- Pydantic v2 models with `model_config = ConfigDict(...)`.
- SQLAlchemy 2.0 async style only.
- `platform-auth` package for JWT — never reimplement auth.
- Error responses in `application/problem+json` format.

**Auth:**
- RS256/JWKS in production. HS256 bridge (`PLATFORM_JWT_SECRET`) is temporary.
- JWKS loading must be async. No `urllib.request` in auth paths.
- Internal endpoints (`/internal/v1/*`) require SERVICE role.
- No optimistic fallback when downstream is unavailable — return 503.

**API:**
- Routes at `/api/v1/{resource}` (public) and `/internal/v1/{resource}` (service-to-service).
- No router prefix — full path in every decorator.
- Health (`/health`), ready (`/ready`), metrics (`/metrics`) at root, no prefix.
- ETag format: `"{version}"` — quoted integer. Must be consistent.
- Idempotency-Key on all POST endpoints.

**Middleware:**
- `BaseHTTPMiddleware` is forbidden. Pure ASGI only.
- RequestIdMiddleware must propagate X-Request-Id and X-Correlation-Id.

**Metrics:**
- Prometheus `endpoint` label uses route template, never raw path.
- High-cardinality data in logs/traces, not metrics.

**Workers:**
- All workers must have graceful shutdown (SIGTERM/SIGINT handlers).
- Outbox: per-event commit, stale claim recovery, Text not JSONB for payload.

---

## Technology Stack

| Layer      | Choice                          |
|------------|---------------------------------|
| Runtime    | Python 3.12+                    |
| Framework  | FastAPI (async ASGI)            |
| ORM        | SQLAlchemy 2.0 (async)         |
| DB Driver  | asyncpg                         |
| Migrations | Alembic                         |
| Database   | PostgreSQL 16+                  |
| IDs        | ULID (python-ulid, 26-char str) |
| HTTP       | httpx.AsyncClient               |
| Validation | Pydantic v2 + pydantic-settings |
| Broker     | confluent-kafka (Redpanda)      |
| Testing    | pytest + pytest-asyncio         |
| Linting    | ruff                            |
| Types      | mypy (strict)                   |

---

## Git & Task Workflow

- Task IDs: `TASK-XXXX`. Next ID in `MEMORY/PROJECT_STATE.md`.
- Commit messages: short imperative, reference task ID.
- Update `MEMORY/PROJECT_STATE.md` when task status changes.
- Do NOT push to remote without explicit user instruction.

---

## What NOT To Do

- Do not add docstrings, comments, or type annotations to code you didn't change.
- Do not add features, refactors, or "improvements" beyond what was asked.
- Do not use `BaseHTTPMiddleware` — pure ASGI only.
- Do not use synchronous I/O in async code paths (urllib, requests).
- Do not bypass auth on internal endpoints.
- Do not use raw URL paths as Prometheus labels.
- Do not skip reading `standards/` before touching code.
