# NEXT_AGENT.md

You are picking up work someone else started.
That person has no memory of writing this.
Read every section. Do not skip. Do not assume.

---

## What This Task Was Trying to Achieve
Ship the P0/P1 release hardening for `location-service` and align `trip-service` with the tightened Location auth and error contract, while deferring P2 cleanup to TASK-0020.

---

## What Was Done
- Added Location bearer-token auth, prod fail-fast config validation, prod docs gating, truthful `/ready`, and a global unexpected-exception problem+json handler.
- Completed the targeted point/pair contract work: `ETag` emission, `If-Match` on pair lifecycle mutations, canonical `/approve` and `/discard`, and a tombstone for `/activate`.
- Fixed live runtime issues in Location: Mapbox GeoJSON parsing, provider config wiring, startup recovery on fresh databases, and the container-only ULID generation crash.
- Updated Trip -> Location auth and error mapping so Location business-invalid responses are not treated as dependency outages; the enrichment worker now skips instead of retrying non-retryable resolution failures.
- Hardened the smoke harness and verified offline + live provider flows end to end.

---

## What Is Not Done Yet
Priority order - most important first.

1. Review TASK-0019 for acceptance.
2. Start TASK-0020 for deferred P2 cleanup only after TASK-0019 is accepted.
3. Decide whether to commit/push these changes; no git write-back was done in this session.

---

## The Riskiest Thing You Need to Know
The worktree still contains unrelated `trip-service` edits outside TASK-0019. Do not fold them into this task by accident.

---

## Other Warnings
- `location-service` processing still uses in-process background tasks plus startup recovery. Persistent worker redesign is still open by design and belongs to TASK-0020.
- The smoke harness now passes, but PowerShell still prints noisy `RemoteException` lines while Alembic INFO logs stream from `docker compose exec`. Treat that as tooling noise, not a failed smoke, unless the script exits non-zero.

---

## Your First Action

1. Read `TASKS/TASK-0019/TEST_EVIDENCE.md`.
2. Review `services/location-service/src/location_service/main.py`, `services/location-service/src/location_service/auth.py`, and `services/trip-service/src/trip_service/dependencies.py`.
3. Check `git status --short` before making any edits so you do not touch unrelated dirty files.

---

## Files Critical to Read Before Coding
- `services/location-service/src/location_service/config.py`
- `services/location-service/src/location_service/main.py`
- `services/location-service/src/location_service/auth.py`
- `services/location-service/src/location_service/processing/pipeline.py`
- `services/location-service/src/location_service/providers/mapbox_directions.py`
- `services/location-service/src/location_service/routers/approval.py`
- `services/location-service/src/location_service/routers/removed_endpoints.py`
- `services/trip-service/src/trip_service/dependencies.py`
- `services/trip-service/src/trip_service/workers/enrichment_worker.py`
- `TASKS/TASK-0012/scripts/smoke.ps1`

---

## Files That Were Changed - Verify Before Adding To
- `services/location-service/tests/conftest.py`
- `services/location-service/tests/test_pairs_api.py`
- `services/location-service/tests/test_processing_flow.py`
- `services/location-service/tests/test_schema_integration.py`
- `services/trip-service/tests/test_integration.py`
- `services/trip-service/tests/test_workers.py`

---

## Open Decisions
- TASK-0020 still needs a final plan before implementation.
- Shared JWT signing domain for Trip/Location is the active deployment assumption; if operations want separate issuers, that is a new decision, not a TASK-0019 bug.

---

## Temporary Implementations

| What | Where | Permanent Solution | Task |
|------|-------|--------------------|------|
| In-process processing recovery instead of a persistent worker | `services/location-service/src/location_service/processing/pipeline.py` | Replace with a DB-backed worker/claim loop | TASK-0020 |

---

## Definition of Done for Remaining Work
- TASK-0019 is accepted as implemented and verified.
- TASK-0020 is opened with a real plan before any P2 cleanup code starts.
- Any commit/push/PR step keeps unrelated dirty files out of scope.
