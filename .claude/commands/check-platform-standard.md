---
description: Audit a service against MEMORY/PLATFORM_STANDARD.md and report violations
---

# Check Platform Standard

Audit one or more services for compliance with `MEMORY/PLATFORM_STANDARD.md`.

## Instructions

1. Read `MEMORY/PLATFORM_STANDARD.md` fully.
2. Read `MEMORY/KNOWN_ISSUES.md` to understand already-tracked drift.
3. Determine scope from user request — single service or all services.

## Checklist per Service

For each service, check:

### Stack (§2)
- [ ] Python 3.12+
- [ ] FastAPI with async handlers
- [ ] SQLAlchemy 2.0 (no legacy Query API)
- [ ] asyncpg driver
- [ ] Alembic migrations (own chain)
- [ ] ULID for IDs (not UUID)
- [ ] Pydantic v2 (`ConfigDict`, not inner `Config`)
- [ ] `httpx.AsyncClient` for outbound HTTP

### Boundaries (§1)
- [ ] No imports from other service packages
- [ ] No cross-database connections
- [ ] ADR-001 respected (Trip → Fleet → Driver, not Trip → Driver)

### Required endpoints (§10)
- [ ] `GET /health` exists and returns 200
- [ ] `GET /ready` exists and checks DB
- [ ] `GET /metrics` exists

### Auth (§4)
- [ ] Uses `platform-auth` for JWT validation
- [ ] No custom JWT implementation

### Error format (§6)
- [ ] Error responses match platform standard format

### Tests (§18)
- [ ] Uses `testcontainers[postgres]` — no mock DB
- [ ] Happy path + 422 + 401 per endpoint

## Report Format

```
=== <service-name> ===
PASS  : <item>
FAIL  : <item> — <what's wrong>
KNOWN : <item> — tracked in KNOWN_ISSUES.md

Summary: X pass, Y fail, Z known
```

## After Audit

- New violations NOT in `KNOWN_ISSUES.md` → add them.
- Ask user if they want to fix violations immediately or create a task.
