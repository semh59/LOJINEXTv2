# NEXT_AGENT.md

You are picking up work someone else started.
That person has no memory of writing this.
Read every section. Do not skip. Do not assume.

---

## What This Task Is Trying to Achieve
Realign trip-service and its location-service dependency to the locked product contract required before a future Tauri desktop app can rely on the backend.

---

## What Was Done This Session
Implemented the TASK-0011 backend contract in trip-service and location-service, rewrote the relevant tests, and verified the scope with passing lint plus automated test runs.

---

## What Is Not Done Yet
Priority order - most important first.

1. Review downstream consumers for contract migration: bearer auth, `route_pair_id` create flows, the new hard-delete path, and the new internal Telegram/Excel endpoints.
2. Decide whether to add a Docker-backed multi-service smoke harness for TASK-0011 or leave that to the future Tauri/client task.
3. Build the actual Tauri desktop client in a follow-up task; TASK-0011 only makes the backend contract ready for it.

---

## The Riskiest Thing You Need to Know
This task intentionally changes the public trip-service contract. Any caller still using `X-Actor-*` headers, raw `route_id` manual creates, or the old hard-delete path will fail until migrated.

---

## Other Warnings

- The worktree is already dirty from prior tasks; do not revert unrelated user changes.
- TASK-0010 is still uncommitted and must remain the implementation base.
- The repository still has no real Tauri frontend code.
- Location-service still has repo-wide lint debt outside the internal-route files touched here; see `MEMORY/KNOWN_ISSUES.md`.

---

## Your First Action

1. Read `TASKS/TASK-0011/STATE.md` and `TEST_EVIDENCE.md`.
2. If you are validating the implementation, rerun `uv run --directory services/trip-service --extra dev pytest`.
3. If you are continuing product work, start from the downstream consumer migration or the follow-up Tauri app task rather than reopening the contract work blindly.

---

## Files Critical to Read Before Coding

- `TASKS/TASK-0011/PLAN.md`
- `TASKS/TASK-0011/STATE.md`
- `TASKS/TASK-0011/TEST_EVIDENCE.md`
- `services/trip-service/src/trip_service/routers/trips.py`
- `services/trip-service/src/trip_service/models.py`
- `services/trip-service/src/trip_service/schemas.py`
- `services/trip-service/tests/conftest.py`
- `services/location-service/src/location_service/routers/internal_routes.py`

---

## Files That Were Changed - Verify Before Adding To

- `MEMORY/DECISIONS.md`
- `MEMORY/PROJECT_STATE.md`
- `TASKS/TASK-0011/BRIEF.md`
- `TASKS/TASK-0011/PLAN.md`
- `TASKS/TASK-0011/STATE.md`
- `TASKS/TASK-0011/CHANGED_FILES.md`
- `TASKS/TASK-0011/TEST_EVIDENCE.md`
- `TASKS/TASK-0011/NEXT_AGENT.md`
- `TASKS/TASK-0011/DONE_CHECKLIST.md`
- `services/trip-service/.env.example`
- `services/trip-service/alembic/versions/a1b2c3d4e5f6_trip_service_baseline.py`
- `services/trip-service/src/trip_service/config.py`
- `services/trip-service/src/trip_service/dependencies.py`
- `services/trip-service/src/trip_service/errors.py`
- `services/trip-service/src/trip_service/models.py`
- `services/trip-service/src/trip_service/routers/driver_statement.py`
- `services/trip-service/src/trip_service/routers/removed_endpoints.py`
- `services/trip-service/src/trip_service/routers/trips.py`
- `services/trip-service/src/trip_service/schemas.py`
- `services/trip-service/src/trip_service/trip_helpers.py`
- `services/trip-service/src/trip_service/workers/enrichment_worker.py`
- `services/trip-service/tests/conftest.py`
- `services/trip-service/tests/test_contract.py`
- `services/trip-service/tests/test_integration.py`
- `services/trip-service/tests/test_migrations.py`
- `services/trip-service/tests/test_unit.py`
- `services/trip-service/tests/test_workers.py`
- `services/location-service/src/location_service/processing/approval.py`
- `services/location-service/src/location_service/routers/internal_routes.py`
- `services/location-service/src/location_service/schemas.py`
- `services/location-service/tests/test_internal_routes.py`

---

## Open Decisions
Questions that need a human to resolve.
If answerable from DECISIONS.md or BRIEF.md, answer yourself.

- None in the implemented contract. Remaining work is execution follow-up, not unresolved product logic.

---

## Temporary Implementations

| What | Where | Permanent Solution | Task |
|------|-------|--------------------|------|
| Docker-backed multi-service smoke harness not added | `TASKS/TASK-0011/TEST_EVIDENCE.md` | Add a disposable integration stack if the team wants pre-release end-to-end smoke outside pytest stubs | follow-up |

---

## Definition of Done for Remaining Work

- No more backend contract work is required for TASK-0011.
- Remaining work is downstream adoption: migrate clients and build the Tauri app against the locked contract.
