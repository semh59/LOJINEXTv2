# PLAN: trip-service Sprint 1-4 Repair

## Context

A comprehensive audit of `trip-service` was provided. After direct code verification, the audit contains significant inaccuracies:

- **BUG-1 (idempotency race)** — ALREADY FIXED in code. `_check_idempotency_key` uses `async_session_factory()` secondary session that commits independently (trip_helpers.py:488-504). Rollback of main transaction cannot affect the placeholder.
- **BUG-2 (cancel_trip bypass)** — ALREADY FIXED in code. `transition_trip()` is called at trips.py:1504. state_machine.py includes `COMPLETED → SOFT_DELETED` and `REJECTED → SOFT_DELETED` transitions.

**Real confirmed bugs and gaps (with exact evidence):**

| # | Severity | Finding | Location |
|---|----------|---------|----------|
| C-1 | Critical | `edit_trip` overlap check skipped when `planned_end_utc is None` | trips.py:1182–1192 |
| C-2 | Critical | `create_trip` / `create_empty_return` pass `planned_end_utc or trip_datetime_utc` — zero-width window, overlap always misses | trips.py:950, 1415 |
| H-1 | High | No HTTP retry on fleet/location calls — single timeout = 503 cascade | http_clients.py:24-28 |
| H-2 | High | No circuit breaker — fleet/location down → all write ops fail | http_clients.py |
| H-3 | High | `enrichment_claim_ttl_seconds=300` vs `dependency_timeout_seconds=5.0` — gap exists but no config validator | config.py:36,23 |
| H-4 | High | Outbox ordering not partition-guaranteed under multi-worker | outbox_relay.py:108 |
| H-5 | High | DLQ silently absorbed — `DEAD_LETTER` status with no alert/webhook | outbox_relay.py:194,219 |
| H-6 | High | Event payload thin (5 fields) — consumers must fan-out GET /trips/{id} | trip_helpers.py:_event_payload |
| M-1 | Medium | No service layer — all business logic in 1596-line god router | routers/trips.py |
| M-2 | Medium | No repository layer — SQL scattered across router + helpers | routers/trips.py + trip_helpers.py |
| M-3 | Medium | `del auth` on list/get/timeline — no row-level isolation | trips.py:1032,1083,1097 |
| M-4 | Medium | `approve_trip` commit has no IntegrityError guard — raw 500 possible | trips.py:1299 |
| M-5 | Medium | `_REFERENCE_EXCLUDED_STATUSES` defined twice — trips.py:125 and trip_helpers.py:46 | dual definition |
| M-6 | Medium | `_coerce_actor_type()` is a no-op (returns `str(role)`) — dead code | trips.py:241-243 |
| M-7 | Medium | Enrichment retry correlation ID set to `enrichment_id`, breaks tracing across retries | enrichment_worker.py:284 |
| L-1 | Low | OCR confidence not range-validated [0.0, 1.0] — data quality truth table breaks on invalid input | enrichment_worker.py:94-118 |
| L-2 | Low | 24-hour fallback for `planned_end_utc=None` in `_find_overlap` is undocumented magic constant | trip_helpers.py:231-234 |
| L-3 | Low | `ingest_trip_slip` creates enrichment with `EnrichmentStatus.READY` but does not resolve route at creation — status is misleading | trips.py:543-553 |
| L-4 | Low | `list_trips` uses offset-based pagination despite CLAUDE.md requiring cursor-based | trips.py:1017-1073 |
| L-5 | Low | `retry_enrichment` resets `enrichment_attempt_count = 0` — allows circumventing max attempt enforcement | trips.py:1585 |

---

## Sprint 1 — Critical: Data Corruption Prevention

### Fix C-1: `edit_trip` overlap guard incorrect

**File:** [services/trip-service/src/trip_service/routers/trips.py](services/trip-service/src/trip_service/routers/trips.py) line 1182

**Problem:** `if overlap_fields & set(changed_fields) and trip.planned_end_utc is not None:` — when `planned_end_utc` is None (fallback trips, incomplete trips), the overlap check is skipped entirely. A driver/vehicle can be double-booked.

**Fix:** Always check overlap when overlap fields change. Use the same 24-hour fallback that `_find_overlap` already uses for the other side of the window:

```python
# BEFORE (line 1182-1192):
if overlap_fields & set(changed_fields) and trip.planned_end_utc is not None:
    await assert_no_trip_overlap(
        ...
        planned_end_utc=trip.planned_end_utc or (trip.trip_datetime_utc + timedelta(hours=24)),
        ...
    )

# AFTER:
if overlap_fields & set(changed_fields):
    await assert_no_trip_overlap(
        ...
        planned_end_utc=trip.planned_end_utc or (trip.trip_datetime_utc + timedelta(hours=24)),
        ...
    )
```

### Fix C-2: Zero-width window in `create_trip` and `create_empty_return`

**File:** [services/trip-service/src/trip_service/routers/trips.py](services/trip-service/src/trip_service/routers/trips.py) lines 950, 1415

**Problem:** `planned_end_utc or trip.trip_datetime_utc` — when `planned_end_utc` is None, `planned_end_utc` arg equals `trip_start_utc`. The overlap window `trip_start < planned_end AND coalesce(existing_end, start+24h) > trip_start` collapses: the new trip window is `[start, start)` (zero-width). `_find_overlap` never sees it as overlapping an existing trip's window. Driver/vehicle can be double-booked at the same instant.

**Fix:** Use `timedelta(hours=24)` fallback, consistent with `_find_overlap`'s COALESCE strategy:

```python
# trips.py:950 — create_trip
planned_end_utc=trip.planned_end_utc or (trip.trip_datetime_utc + timedelta(hours=24)),

# trips.py:1415 — create_empty_return
planned_end_utc=trip.planned_end_utc or (trip.trip_datetime_utc + timedelta(hours=24)),
```

---

## Sprint 2 — High: Reliability

### Fix H-1: HTTP retry with tenacity

**File:** [services/trip-service/src/trip_service/http_clients.py](services/trip-service/src/trip_service/http_clients.py)

Add `tenacity` retry decorator (3 attempts, exponential backoff 0.5s→1s→2s) around fleet/location HTTP calls in [services/trip-service/src/trip_service/dependencies.py](services/trip-service/src/trip_service/dependencies.py). Only retry on `httpx.TransportError` and 5xx status codes, not on 4xx (those are caller errors).

```python
# dependencies.py — wrap validate_trip_references, fetch_trip_context, resolve_route_by_names
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    retry=retry_if_exception_type(httpx.TransportError),
    reraise=True,
)
async def _fleet_post_with_retry(client, url, payload, headers): ...
```

Add `tenacity` to `pyproject.toml` dependencies.

### Fix H-2: Circuit breaker

Implement a simple in-process circuit breaker (half-open after 30s, 5 consecutive failures trip) in `http_clients.py` using a per-service state object. Alternatively, use `tenacity`'s `CircuitBreaker` strategy. This prevents cascade when fleet/location is down.

### Fix H-3: Config validator for enrichment TTL vs HTTP timeout

**File:** [services/trip-service/src/trip_service/config.py](services/trip-service/src/trip_service/config.py)

Add a `@model_validator(mode='after')` check: `dependency_timeout_seconds * 3 < enrichment_claim_ttl_seconds`. The TTL must be large enough to cover worst-case retry (3 attempts × timeout). Currently 5s × 3 = 15s << 300s — this is fine, but a future config change could break it.

### Fix H-5: DLQ alerting

**File:** [services/trip-service/src/trip_service/workers/outbox_relay.py](services/trip-service/src/trip_service/workers/outbox_relay.py) line 219

The `logger.error(...)` on DEAD_LETTER is present but insufficient. Add a structured log tag `"alert": "DEAD_LETTER"` so log aggregators (Loki/Datadog) can route it. Document this in MEMORY/KNOWN_ISSUES.md as needing a real alerting hook.

### Fix H-6: Enrich event payload

**File:** [services/trip-service/src/trip_service/trip_helpers.py](services/trip-service/src/trip_service/trip_helpers.py) — `_event_payload()` function

Add `driver_id`, `vehicle_id`, `trailer_id`, `route_id`, `origin_location_id`, `destination_location_id`, `trip_datetime_utc` to the payload dict so downstream consumers don't need GET /trips/{id}.

---

## Sprint 3 — Medium: Maintainability

### Fix M-4: `approve_trip` missing IntegrityError guard

**File:** [services/trip-service/src/trip_service/routers/trips.py](services/trip-service/src/trip_service/routers/trips.py) line 1299

Wrap `await session.commit()` in `try/except IntegrityError` with rollback + `_map_integrity_error()`, consistent with all other create endpoints.

### Fix M-5: Deduplicate `_REFERENCE_EXCLUDED_STATUSES`

Defined at trips.py:125 and trip_helpers.py:46. Remove the one in trips.py and import from trip_helpers.py.

### Fix M-1/M-2: Service/Repository layer extraction (sprint 3 — large refactor)

Extract `TripWriteService` and `TripRepository` from the 1596-line router. The 4 create flows share trip construction logic that diverges only in source type and field population. Repository should own all `select(TripTrip)` queries.

**This is a large refactor; defer to sprint 3 after bugs are fixed.**

---

## Sprint 4 — Observability

### Fix H-4: Outbox ordering

**File:** [services/trip-service/src/trip_service/workers/outbox_relay.py](services/trip-service/src/trip_service/workers/outbox_relay.py)

Current `ORDER BY created_at_utc ASC` does not guarantee causal ordering per trip under multi-worker. Mitigation: partition claim by `aggregate_id % worker_count` (requires config plumbing). Document current risk in MEMORY/KNOWN_ISSUES.md.

### Fix M-7: Enrichment correlation ID

**File:** [services/trip-service/src/trip_service/workers/enrichment_worker.py](services/trip-service/src/trip_service/workers/enrichment_worker.py) line 284

Set correlation ID to `trip_id` (stable across retries), not `enrichment_id` (new per attempt). This makes log traces joinable across enrichment retry attempts.

### Fix L-4: Cursor-based pagination for `list_trips`

**File:** [services/trip-service/src/trip_service/routers/trips.py](services/trip-service/src/trip_service/routers/trips.py) line 1017

CLAUDE.md §API Design mandates cursor-based pagination. Current offset pagination is fragile under concurrent inserts. Migrate to `cursor = (trip_datetime_utc, id)` after sprint 3 refactor.

---

## Critical Files

| File | Relevance |
|------|-----------|
| [services/trip-service/src/trip_service/routers/trips.py](services/trip-service/src/trip_service/routers/trips.py) | Lines 950, 1182-1192, 1299, 1415 — direct bug sites |
| [services/trip-service/src/trip_service/trip_helpers.py](services/trip-service/src/trip_service/trip_helpers.py) | `_event_payload`, `_REFERENCE_EXCLUDED_STATUSES`, `_find_overlap` |
| [services/trip-service/src/trip_service/http_clients.py](services/trip-service/src/trip_service/http_clients.py) | No retry, no circuit breaker |
| [services/trip-service/src/trip_service/dependencies.py](services/trip-service/src/trip_service/dependencies.py) | Fleet/location call sites for retry wrapping |
| [services/trip-service/src/trip_service/config.py](services/trip-service/src/trip_service/config.py) | Config validator for TTL/timeout |
| [services/trip-service/src/trip_service/workers/outbox_relay.py](services/trip-service/src/trip_service/workers/outbox_relay.py) | DLQ alert, ordering |
| [services/trip-service/src/trip_service/workers/enrichment_worker.py](services/trip-service/src/trip_service/workers/enrichment_worker.py) | Correlation ID fix |
| [services/trip-service/src/trip_service/state_machine.py](services/trip-service/src/trip_service/state_machine.py) | Verified correct — do not touch |

---

## What NOT to Fix (Verified Correct in Code)

- BUG-1 idempotency race: `secondary_session` already isolates placeholder commit
- BUG-2 cancel_trip bypass: `transition_trip()` already called, state machine has all transitions
- BUG-7 enrichment retry indexing: comment `# BUG-07 fix` confirms already resolved

---

## Verification

### Sprint 1 (C-1, C-2)
1. Create a fallback trip (no `planned_end_utc`).
2. Edit the trip to assign a driver already on another active trip at the same time.
3. **Expect:** 409 Conflict. **Before fix:** 200 OK (overlap missed).
4. Create two manual trips for the same driver at overlapping times with `planned_end_utc=None`.
5. **Expect:** 409 on second create. **Before fix:** Both accepted.

### Sprint 2 (H-1)
1. Start service with fleet-service unreachable.
2. Call `POST /api/v1/trips` — expect retry logs then `503` dependency unavailable.
3. **Before fix:** Immediate 503 on first attempt.

### Sprint 3 (M-4)
1. Manufacture a COMPLETED trip with a `trip_no` that already exists (direct DB insert).
2. Call `POST /api/v1/trips/{id}/approve` — expect 409 conflict.
3. **Before fix:** raw 500 from unhandled IntegrityError.

### All sprints
```bash
cd services/trip-service && pytest
```
