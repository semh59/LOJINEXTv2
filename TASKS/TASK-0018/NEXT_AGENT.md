# NEXT_AGENT.md

You are picking up work someone else started.
That person has no memory of writing this.
Read every section. Do not skip. Do not assume.

---

## What This Task Is Trying to Achieve
Remove Location Service import/export ownership and tighten the remaining route-authority contracts without touching Trip Service.

---

## What Was Done This Session
- Removed `POST /v1/import` and `GET /v1/export` from `services/location-service`, deleted the related router/processing files, removed the dead config/dependencies/metrics, and added `services/location-service/alembic/versions/0d5f12e97db6_remove_import_export.py`.
- Added a generic FastAPI request-validation -> `application/problem+json` handler, tightened point integrity/error mapping, made pair patch use `If-Match`, enforced pair `row_version` increments across patch/delete/approve/discard/pipeline mutations, and tightened calculate/refresh guards.
- Reworked `/internal/v1/routes/resolve` to return only ACTIVE route-version candidates and to fail with `ROUTE_AMBIGUOUS` when multiple active candidates exist.
- Rebuilt the Location Service tests around the new contract and verified `uv run ruff check src tests`, `uv run pytest`, and Alembic upgrade on disposable PostgreSQL.

---

## What Is Not Done Yet
Priority order - most important first.

1. Review the contract changes and migration for acceptance.
2. Decide whether TASK-0018 should be committed/pushed or kept for more review.
3. Coordinate any downstream communication for the removed import/export surface if external callers still exist.

---

## The Riskiest Thing You Need to Know
`trip-service` files in the worktree were already dirty before TASK-0018. They were inspected, confirmed out of scope, and intentionally left untouched. Do not mix them into this task by accident.

---

## Other Warnings
- Pair `row_version` behavior is now materially different; if another task mutates pair state, it must keep increment semantics intact.
- The processing pipeline now persists `forward_route_id` / `reverse_route_id` back onto the pair; future changes to pipeline/approval must preserve that contract.

---

## Your First Action

1. Read `TASKS/TASK-0018/TEST_EVIDENCE.md`.
2. Review `services/location-service/src/location_service/routers/pairs.py` and `services/location-service/src/location_service/routers/internal_routes.py`.
3. Check `git status --short` before making any further edits so you do not touch unrelated `trip-service` work.

---

## Files Critical to Read Before Coding
- `services/location-service/src/location_service/errors.py`
- `services/location-service/src/location_service/routers/points.py`
- `services/location-service/src/location_service/routers/pairs.py`
- `services/location-service/src/location_service/routers/processing.py`
- `services/location-service/src/location_service/routers/internal_routes.py`
- `services/location-service/src/location_service/processing/pipeline.py`
- `services/location-service/alembic/versions/0d5f12e97db6_remove_import_export.py`

---

## Files That Were Changed - Verify Before Adding To
- `services/location-service/src/location_service/processing/approval.py`
- `services/location-service/src/location_service/routers/approval.py`
- `services/location-service/tests/test_pairs_api.py`
- `services/location-service/tests/test_internal_routes.py`
- `services/location-service/tests/conftest.py`

---

## Open Decisions
- No unresolved product decision remains inside TASK-0018 itself.
- Human review is still needed if the team wants a commit/push/PR in this session.

---

## Temporary Implementations

| What | Where | Permanent Solution | Task |
|------|-------|--------------------|------|
| None | - | - | - |

---

## Definition of Done for Remaining Work
- Reviewer confirms the contract changes are acceptable.
- If desired, commit/push/PR steps happen without pulling unrelated `trip-service` changes into the task.
