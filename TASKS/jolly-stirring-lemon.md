# TASK-0052: Fleet Service Production Hardening — Comprehensive Bug Fix

**Status:** planned  
**Priority:** high  
**Task ID:** TASK-0052

---

## Context

Fleet-service is the most architecturally mature service in the platform (layered domain/services/repos/schemas, ETag locking, transactional outbox, spec versioning). However, the audit file provided by the user (AUDIT-fleet-service.md) identified 4 critical/high bugs, and a deep read of the code against PLATFORM_STANDARD.md §21 reveals additional platform-standard deviations that are now binding.

This task fixes all confirmed bugs and applies the full PLATFORM_STANDARD.md transition backlog for fleet-service.

---

## Confirmed Bugs (Code-Verified)

### BUG-1 (CRITICAL): `patch_vehicle` audit snapshot captured after plate mutation

**File:** [services/fleet-service/src/fleet_service/services/vehicle_service.py](services/fleet-service/src/fleet_service/services/vehicle_service.py#L381-L390)

**Evidence:**
```python
# Line 381-387: plate applied to vehicle object
vehicle.plate_raw_current = body.plate
vehicle.normalized_plate_current = new_normalized
changes["plate"] = body.plate
# Line 390: snapshot AFTER mutation — old_snapshot contains the NEW plate!
old_snapshot = serialize_vehicle_admin(vehicle)
```

**Fix:** Move `old_snapshot = serialize_vehicle_admin(vehicle)` to line 378 (before ANY field mutation), just after the ETag/soft-delete guards.

**Same bug in trailer:** [services/fleet-service/src/fleet_service/services/trailer_service.py](services/fleet-service/src/fleet_service/services/trailer_service.py#L365-L372) — `patch_trailer` applies plate changes (lines 365-371) but **does NOT even call `_write_fleet_audit`** at all. Audit write is completely absent from `patch_trailer`. This is worse than vehicle — no audit record is created.

---

### BUG-2 (CONFIRMED FIXED in code): `validate_trip_compat_contract` — DependencyUnavailableError handling

**File:** [services/fleet-service/src/fleet_service/services/internal_service.py](services/fleet-service/src/fleet_service/services/internal_service.py#L231-L247)

**Status:** ✅ Already fixed. Lines 231-247 show `try/except DependencyUnavailableError` with optimistic fallback. The audit report was based on an earlier version. **No action needed.**

---

### BUG-3 (CONFIRMED): `patch_trailer` — no audit log written

**File:** [services/fleet-service/src/fleet_service/services/trailer_service.py](services/fleet-service/src/fleet_service/services/trailer_service.py#L399-L444)

After `update_trailer` (line 395), the function inserts timeline + outbox events but **never calls `_write_fleet_audit`**. The vehicle equivalent (vehicle_service.py:438-450) does call it. This is an asymmetry bug — trailer patches produce no audit record.

**Fix:** Add `_write_fleet_audit` call in `patch_trailer`, mirroring `patch_vehicle`'s pattern, after capturing `old_snapshot` before mutations.

---

### BUG-4 (CONFIRMED): `spec_versions` relationship — wrong lazy strategy

**File:** [services/fleet-service/src/fleet_service/models.py](services/fleet-service/src/fleet_service/models.py#L70)

```python
spec_versions: Mapped[list[FleetVehicleSpecVersion]] = relationship(back_populates="vehicle", lazy="raise")
```

**Status:** ✅ Already `lazy="raise"` on both `FleetVehicle.spec_versions` (line 70) and `FleetTrailer.spec_versions` (line 116). The audit report described `lazy="selectin"` but the current code has `lazy="raise"`. **No action needed.**

---

### BUG-5 (NEW): `BaseHTTPMiddleware` — asyncpg hang risk

**File:** [services/fleet-service/src/fleet_service/middleware.py](services/fleet-service/src/fleet_service/middleware.py)

Both `RequestIdMiddleware` and `PrometheusMiddleware` extend `BaseHTTPMiddleware`. Per PLATFORM_STANDARD.md §11, `BaseHTTPMiddleware` causes request hangs under load with asyncpg due to response streaming interference. Must be replaced with pure ASGI middleware.

---

### BUG-6 (NEW): Error `type` URL uses service-local domain

**File:** [services/fleet-service/src/fleet_service/errors.py](services/fleet-service/src/fleet_service/errors.py#L305)

```python
"type": f"https://fleet-service/errors/{exc.code}",
```

**Required (PLATFORM_STANDARD.md §6):**
```python
"type": f"https://errors.lojinext.com/{exc.code}",
```

---

### BUG-7 (NEW): `detail` field in error responses is conditionally omitted

**File:** [services/fleet-service/src/fleet_service/errors.py](services/fleet-service/src/fleet_service/errors.py#L311-L312)

```python
if exc.detail:
    body["detail"] = exc.detail
```

PLATFORM_STANDARD.md §6 requires `detail` to always be a `str`, never absent. When `exc.detail` is `None`, the key is omitted entirely. Fix: always emit `detail`, defaulting to `""` if `None`.

---

### BUG-8 (NEW): `validate_prod_settings` does not reject `PLATFORM_JWT_SECRET` in prod

**File:** [services/fleet-service/src/fleet_service/config.py](services/fleet-service/src/fleet_service/config.py#L104-L138)

The auth bridge in `auth.py` (lines 79-87) correctly skips HS256 bridge when `environment == "prod"`, but `validate_prod_settings` has no explicit check to reject if `platform_jwt_secret` is set in prod. Add a guard: if `current.platform_jwt_secret and current.environment == "prod"` → error.

---

### BUG-9 (NEW): Outbox model missing `partition_key`, `claim_token`, `claimed_by_worker` fields

**File:** [services/fleet-service/src/fleet_service/models.py](services/fleet-service/src/fleet_service/models.py#L290-L309)

PLATFORM_STANDARD.md §9 canonical field set requires:
- `partition_key` — **missing** (routing key for Kafka partitioning)
- `claim_token` — **missing** (worker identity claim for crash recovery)
- `claimed_by_worker` — **missing** (worker ID for claim ownership)

`payload_json` is `JSONB` but standard requires `Text`. This is a schema-level drift requiring Alembic migration.

---

### BUG-10 (NEW): Outbox relay does not set `claim_token` / `claimed_by_worker` on claim

**File:** [services/fleet-service/src/fleet_service/repositories/outbox_repo.py](services/fleet-service/src/fleet_service/repositories/outbox_repo.py#L84-L92)

`claim_batch` sets `PUBLISHING` + `claim_expires_at_utc` but does not set `claim_token` or `claimed_by_worker`. Once the model fields exist (BUG-9 migration), relay must populate them for proper crash recovery semantics.

---

### BUG-11 (NEW): ISSUE-003 — `initial_spec` fields silently ignored on vehicle/trailer create

**File:** MEMORY/KNOWN_ISSUES.md (ISSUE-003, open)

When creating a vehicle or trailer, the request body accepts `initial_spec` fields but they are never applied. The asset is created without a spec version. Callers must make a separate `POST /spec-versions` call. This breaks the contract implied by the create API and blocks fuel-metadata resolution immediately after create.

**Fix:** In `create_vehicle` and `create_trailer`, if `body.initial_spec` is not None, call the spec creation logic within the same transaction after the vehicle/trailer row is committed.

---

## Platform-Standard Deviations (from §21 Transition Backlog)

These are PLATFORM_STANDARD.md violations that must be resolved in this task:

| # | Item | File | Status |
|---|------|------|--------|
| D-1 | Middleware: `BaseHTTPMiddleware` → pure ASGI | middleware.py | ❌ BUG-5 above |
| D-2 | Error `type` URL → `https://errors.lojinext.com/{CODE}` | errors.py | ❌ BUG-6 above |
| D-3 | `detail: str \| None` → always `str` | errors.py | ❌ BUG-7 above |
| D-4 | Config: reject `PLATFORM_JWT_SECRET` in prod | config.py | ❌ BUG-8 above |
| D-5 | Outbox: `payload_json` JSONB → Text | models.py + migration | ❌ BUG-9 above |
| D-6 | Outbox: add `partition_key`, `claim_token`, `claimed_by_worker` | models.py + migration | ❌ BUG-9 above |
| D-7 | Outbox relay: populate `claim_token`/`claimed_by_worker` | outbox_repo.py | ❌ BUG-10 above |
| D-8 | ISSUE-003: `initial_spec` applied on create | vehicle/trailer_service | ❌ BUG-11 above |
| D-9 | Health router: verify no `/v1` prefix | health.py | ✅ Already correct (`/health`, `/ready`, `/metrics`) |
| D-10 | Roles: `ActorType` vs `PlatformRole` | enums.py | ℹ️ fleet-service defines its own `ActorType` with ADMIN/MANAGER/SUPER_ADMIN/SERVICE/SYSTEM — matches platform roles in practice but not imported from platform-common. Defer to separate role alignment task. |

---

## Out of Scope (Deferred)

- **H-1** Hard delete idempotency key — low blast radius, separate task
- **H-2** `event_version` config-driven — config field `schema_event_version` already exists; only hardening needed
- **H-3** DLQ alerting — infra-level concern, not code
- **BUG-1 (circuit breaker multi-process)** — `asyncio.Lock()` is already present in both clients (lines 28-29 of driver_client.py and trip_client.py). The lock correctly serializes within-process access. True multi-process shared state (Redis/PG) is an infra hardening concern, not an immediate code bug. Defer.

---

## Implementation Plan

### Step 1: Fix `patch_vehicle` audit snapshot ordering

**File:** [services/fleet-service/src/fleet_service/services/vehicle_service.py](services/fleet-service/src/fleet_service/services/vehicle_service.py)

Move the import and `old_snapshot` capture to line 378 (just after the `VehicleSoftDeletedError` guard), before any field is mutated. The import can move to the top of the file.

```python
# After soft-delete guard (line 375), before any changes:
from fleet_service.services.audit_helpers import _write_fleet_audit, serialize_vehicle_admin
old_snapshot = serialize_vehicle_admin(vehicle)

now = _utc_now()
changes: dict[str, Any] = {}

# Apply changes...
if body.plate is not None:
    ...
```

### Step 2: Fix `patch_trailer` — capture snapshot + add audit write

**File:** [services/fleet-service/src/fleet_service/services/trailer_service.py](services/fleet-service/src/fleet_service/services/trailer_service.py)

1. Move import to top of file
2. Capture `old_snapshot = serialize_trailer_admin(trailer)` before plate/field mutations (after soft-delete guard)
3. After `update_trailer` and before `session.commit()`, add `_write_fleet_audit(...)` call mirroring vehicle's pattern

Check if `serialize_trailer_admin` exists in [services/fleet-service/src/fleet_service/services/audit_helpers.py](services/fleet-service/src/fleet_service/services/audit_helpers.py). If not, add it.

### Step 3: Fix error response format

**File:** [services/fleet-service/src/fleet_service/errors.py](services/fleet-service/src/fleet_service/errors.py)

Two changes in `problem_detail_handler`:
```python
# Change type URL:
"type": f"https://errors.lojinext.com/{exc.code}",
# Always emit detail:
"detail": exc.detail or "",
```

Remove the `if exc.detail:` guard.

### Step 4: Fix `validate_prod_settings` — reject PLATFORM_JWT_SECRET in prod

**File:** [services/fleet-service/src/fleet_service/config.py](services/fleet-service/src/fleet_service/config.py)

Add to `validate_prod_settings`:
```python
if current.platform_jwt_secret:
    errors.append("FLEET_PLATFORM_JWT_SECRET must not be set in prod; use RS256/JWKS only.")
```

### Step 5: Replace `BaseHTTPMiddleware` with pure ASGI middleware

**File:** [services/fleet-service/src/fleet_service/middleware.py](services/fleet-service/src/fleet_service/middleware.py)

Replace both classes with pure ASGI implementations using `starlette.types.ASGIApp, Scope, Receive, Send`. Pattern:

```python
class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        # extract / generate correlation_id, set on scope["state"]
        # wrap send to inject X-Correlation-ID response header
        ...
```

Refer to existing pure-ASGI implementations in location-service or identity-service for the exact send-wrapper pattern used across the platform.

### Step 6: Outbox model schema migration

**Files:**
- [services/fleet-service/src/fleet_service/models.py](services/fleet-service/src/fleet_service/models.py) — `FleetOutbox`
- New Alembic migration file

Model changes to `FleetOutbox`:
1. `payload_json: Mapped[str]` → `Text` (not JSONB)
2. Add `partition_key: Mapped[str | None]` — `String(100)`
3. Add `claim_token: Mapped[str | None]` — `String(50)`
4. Add `claimed_by_worker: Mapped[str | None]` — `String(50)`

Migration must include:
- `upgrade()`: `ALTER TABLE fleet_outbox ALTER COLUMN payload_json TYPE TEXT USING payload_json::text`, plus `ADD COLUMN` for the three new fields
- `downgrade()`: reverse type cast + drop columns

All existing `payload_json={...}` dict assignments in vehicle_service, trailer_service must be updated to `json.dumps({...})` since the column is now `Text`.

### Step 7: Outbox relay — populate claim fields

**File:** [services/fleet-service/src/fleet_service/repositories/outbox_repo.py](services/fleet-service/src/fleet_service/repositories/outbox_repo.py)

In `claim_batch`, add `claim_token` (generate `str(ULID())`) and `claimed_by_worker` (use `settings.service_name` or worker instance ID) to the UPDATE values.

In `mark_published` and `mark_dead_letter`, clear `claim_token=None, claimed_by_worker=None`.

In `mark_failed`, clear `claim_token=None, claimed_by_worker=None`.

### Step 8: Fix ISSUE-003 — apply `initial_spec` on create

**Files:**
- [services/fleet-service/src/fleet_service/services/vehicle_service.py](services/fleet-service/src/fleet_service/services/vehicle_service.py) — `create_vehicle`
- [services/fleet-service/src/fleet_service/services/trailer_service.py](services/fleet-service/src/fleet_service/services/trailer_service.py) — `create_trailer`

After the vehicle/trailer master row is created and the idempotency record written, check if `body.initial_spec is not None`. If so, call the spec creation logic (reuse `vehicle_spec_service.create_vehicle_spec_version` or inline the equivalent steps) within the same transaction. Return the spec ETag in the response.

This resolves KNOWN_ISSUES.md ISSUE-003 — mark it closed after implementation.

---

## Critical Files to Modify

| File | Changes |
|------|---------|
| [services/fleet-service/src/fleet_service/services/vehicle_service.py](services/fleet-service/src/fleet_service/services/vehicle_service.py) | BUG-1 (snapshot ordering), Step 8 (initial_spec) |
| [services/fleet-service/src/fleet_service/services/trailer_service.py](services/fleet-service/src/fleet_service/services/trailer_service.py) | BUG-3 (audit write), snapshot ordering, Step 8 |
| [services/fleet-service/src/fleet_service/services/audit_helpers.py](services/fleet-service/src/fleet_service/services/audit_helpers.py) | Add `serialize_trailer_admin` if missing |
| [services/fleet-service/src/fleet_service/errors.py](services/fleet-service/src/fleet_service/errors.py) | Step 3 (error type URL + detail always str) |
| [services/fleet-service/src/fleet_service/config.py](services/fleet-service/src/fleet_service/config.py) | Step 4 (reject PLATFORM_JWT_SECRET in prod) |
| [services/fleet-service/src/fleet_service/middleware.py](services/fleet-service/src/fleet_service/middleware.py) | Step 5 (pure ASGI) |
| [services/fleet-service/src/fleet_service/models.py](services/fleet-service/src/fleet_service/models.py) | Step 6 (outbox schema) |
| [services/fleet-service/src/fleet_service/repositories/outbox_repo.py](services/fleet-service/src/fleet_service/repositories/outbox_repo.py) | Step 7 (claim fields) |
| New Alembic migration | Step 6 (payload_json + 3 new outbox columns) |
| [MEMORY/KNOWN_ISSUES.md](MEMORY/KNOWN_ISSUES.md) | Close ISSUE-003 after Step 8 |
| [MEMORY/PROJECT_STATE.md](MEMORY/PROJECT_STATE.md) | Advance next task ID to TASK-0053, mark TASK-0052 complete |

---

## Implementation Order

Execute steps in this order to avoid cascading breaks:

1. Step 3 (errors.py) — standalone, no deps
2. Step 4 (config.py) — standalone, no deps
3. Step 1 (vehicle_service snapshot) — isolated to one function
4. Step 3b (audit_helpers — check/add serialize_trailer_admin)
5. Step 3c (trailer_service — snapshot + audit write) — depends on audit_helpers check
6. Step 5 (middleware pure ASGI) — standalone
7. Step 6 (models.py outbox schema) — must come before migration
8. New Alembic migration — after model changes; update all `payload_json={...}` → `json.dumps(...)` calls in services
9. Step 7 (outbox_repo claim fields) — after migration
10. Step 8 (initial_spec on create) — last; touches most files

---

## Verification

### Automated checks (per PLATFORM_STANDARD.md §18 CI gates)
```bash
cd services/fleet-service
ruff check src tests
mypy src/fleet_service --ignore-missing-imports
alembic upgrade head
alembic downgrade -1
alembic upgrade head
pytest tests -v
```

### Manual contract checks
1. `PATCH /api/v1/vehicles/{id}` with plate change → audit log `old_snapshot_json.plate` must be the **original** plate
2. `PATCH /api/v1/trailers/{id}` → audit log entry must exist in `fleet_audit_log`
3. Any 4xx error response → `type` field must be `https://errors.lojinext.com/{CODE}`, `detail` must always be present (even as `""`)
4. `FLEET_PLATFORM_JWT_SECRET` set with `FLEET_ENVIRONMENT=prod` → service must refuse to start
5. `POST /api/v1/vehicles` with `initial_spec` body → response includes spec ETag, `GET /spec/current` works immediately
6. `/health`, `/ready`, `/metrics` must respond at root paths (already correct — verify unchanged)
7. Under load: middleware must not hang asyncpg connections (smoke test with concurrent requests)
8. Outbox rows in `fleet_outbox` must show `claim_token` + `claimed_by_worker` populated when in `PUBLISHING` state
