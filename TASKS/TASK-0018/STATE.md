# STATE.md

## Status
[ ] new
[ ] reading
[ ] planning
[ ] in_progress
[ ] blocked
[ ] ready_for_review
[x] done

## Last Updated
Date: 2026-03-28
Agent: Codex

---

## Progress Against Plan

| Step | Status |
|------|--------|
| 1. Open task records and memory updates | done |
| 2. Remove import/export surface | done |
| 3. Tighten request validation and point errors | done |
| 4. Tighten pair/process/resolve contracts | done |
| 5. Update tests and verify | done |

---

## Completed This Session

- Removed `POST /v1/import` and `GET /v1/export` from Location Service, deleted the related router/processing files, removed the runtime dependencies, and added a forward Alembic cleanup migration.
- Tightened public contracts for points, pairs, processing, approval, and internal resolve/trip-context, including problem+json validation handling, pair `row_version` semantics, and ACTIVE-version-only resolution.
- Rebuilt the Location Service test suite around the new contract and verified `ruff`, `pytest`, and `alembic upgrade head` against disposable PostgreSQL.

---

## Still Open

- No open implementation work in TASK-0018.

---

## Blocked
[ ] Yes
[x] No

What is blocking:
What is needed:
Who resolves it:

---

## Risks Found During Build

- `trip-service` worktree changes remain unrelated and intentionally untouched; they still need their own owner/review path outside TASK-0018.

---

## Unexpected Findings

- `RoutePair.row_version` was effectively dead before this task; approval, discard, delete, and pipeline draft-pointer mutations all needed explicit increments.
- The processing pipeline was not persisting `forward_route_id` / `reverse_route_id` back onto the pair, which would have undermined resolve/trip-context correctness after successful calculations.
