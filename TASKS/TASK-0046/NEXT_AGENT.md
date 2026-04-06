# NEXT_AGENT.md

## Task Goal
Complete the real `trip-service` backfill gate for the landed Phase A repair and determine whether Phase B strict cleanup is now eligible.

## What Was Done
- Created the dedicated `TASK-0046` handoff for the already-landed `trip-service` Phase A patch.
- Recorded the full Phase A patch surface in `CHANGED_FILES.md`.
- Re-ran the local validation commands:
  - `uv sync --extra dev`
  - `uv run ruff check src tests`
  - `uv run pytest -q` -> `94 passed`
  - route smoke from `trip_service.main`
- Re-ran `uv run python scripts/backfill_trip_status_drift.py --dry-run` against the configured DB and confirmed the blocker persists: `ConnectionRefusedError` at `127.0.0.1:5433`.
- Reproduced the backfill `--dry-run` successfully against an ephemeral migrated Postgres instance to prove the repo-side script and schema path are healthy.

## What Is Not Done Yet
1. Restore connectivity to the configured `trip-service` database.
2. Run `uv run python scripts/backfill_trip_status_drift.py --dry-run` against the real target DB.
3. If and only if the dry-run exits `0` and reports `blocking_rows=[]`, run `uv run python scripts/backfill_trip_status_drift.py --apply`.
4. Run a second real-DB `--dry-run` and require `remaining_counts={}` before declaring the task ready for review.
5. Open a separate follow-up task for Phase B strict cleanup only after the verification dry-run is clean.

## The Riskiest Thing You Need to Know
Do not treat the green unit/integration test suite as permission to run Phase B. The real DB gate is still closed, and that is the only valid blocker between the landed code patch and strict legacy-status cleanup.

## Other Warnings
- `TASK-0045` is a separate cross-service recovery record. Do not fold this work back into it.
- The current route smoke output includes both `/api/v1/trips/{trip_id}/hard` and `/api/v1/trips/{trip_id}/hard-delete`. This task records reality and does not reinterpret that alias.
- The configured DB failure is environmental. Do not patch `trip-service` code in response to the `ConnectionRefusedError`.

## Your First Action
1. Verify the target DB host/port for `trip-service` is reachable from the current environment.
2. Run `uv run python scripts/backfill_trip_status_drift.py --dry-run`.
3. Stop immediately if the command fails to connect or if it reports `REQUESTED` / `IN_PROGRESS` rows.

## Files Critical to Read Before Coding
- `TASKS/TASK-0046/TEST_EVIDENCE.md`
- `TASKS/TASK-0046/STATE.md`
- `TASKS/TASK-0046/CHANGED_FILES.md`
- `services/trip-service/scripts/backfill_trip_status_drift.py`
- `services/trip-service/src/trip_service/routers/trips.py`
- `services/trip-service/src/trip_service/trip_helpers.py`

## Files That Were Changed - Verify Before Adding To
- `MEMORY/PROJECT_STATE.md`
- `services/trip-service/Dockerfile`
- `services/trip-service/pyproject.toml`
- `services/trip-service/src/trip_service/config.py`
- `services/trip-service/src/trip_service/enums.py`
- `services/trip-service/src/trip_service/routers/health.py`
- `services/trip-service/src/trip_service/routers/trips.py`
- `services/trip-service/src/trip_service/state_machine.py`
- `services/trip-service/src/trip_service/trip_helpers.py`
- `services/trip-service/scripts/backfill_trip_status_drift.py`
- `services/trip-service/tests/conftest.py`
- `services/trip-service/tests/test_backfill_status_drift.py`
- `services/trip-service/tests/test_config.py`
- `services/trip-service/tests/test_contract.py`
- `services/trip-service/tests/test_integration.py`
- `services/trip-service/tests/test_migrations.py`
- `services/trip-service/tests/test_runtime.py`
- `services/trip-service/tests/test_unit.py`

## Open Decisions
- None inside `TASK-0046`. The remaining gate is operational access to the real database, not a product or code decision.

## Temporary Implementations

| What | Where | Permanent Solution | Task |
|------|-------|--------------------|------|
| Transitional legacy-status compat for raw `CANCELLED` rows | `services/trip-service/src/trip_service/routers/trips.py`, `services/trip-service/src/trip_service/trip_helpers.py` | Remove compat branches only after a clean real-DB backfill and verification. | Future Phase B follow-up |

## Definition of Done for Remaining Work
- Real DB `--dry-run` exits `0` and reports no blocking rows.
- Real DB `--apply` succeeds.
- Real DB verification `--dry-run` reports `remaining_counts={}`.
- `TASKS/TASK-0046/STATE.md` and `TEST_EVIDENCE.md` are updated with the real DB outputs.
- A separate Phase B follow-up is either opened or explicitly deferred with reason.
