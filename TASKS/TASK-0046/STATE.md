# STATE.md

## Status
[ ] new
[ ] reading
[ ] planning
[x] in_progress
[ ] blocked
[ ] ready_for_review
[ ] done

## Last Updated
Date: 2026-04-05
Agent: Codex

---

## Progress Against Plan

| Step | Status |
|------|--------|
| 1. Reconstruct the landed `trip-service` Phase A patch surface and evidence in task records. | done |
| 2. Implement the deep local validation plan and close any repo-side regressions discovered by new tests. | done |
| 3. Re-run the configured DB `--dry-run` and record the real gate state. | done |
| 4. Run target DB `--apply` and verification `--dry-run` once the configured DB is reachable. | not started |

---

## Completed This Session
- Created the dedicated `TASK-0046` task record set for the `trip-service` Phase A repair follow-up.
- Implemented the deep test plan inside `services/trip-service/`:
  - added new deep suites for `auth`, `dependencies`, `broker`, `http_clients`, `observability`, `entrypoints`, and `timezones`
  - expanded `unit`, `contract`, `integration`, `worker`, `runtime`, and `backfill` suites
  - fixed repo-side bugs found by the new tests:
    - production RS256 config validation now rejects missing issuer/audience
    - dependency parsing now converts malformed downstream payloads into stable dependency errors
    - enrichment worker now awaits the location-service auth header helper before calling Location
- Refreshed the validation evidence:
  - `uv sync --extra dev`
  - `uv run ruff check src tests`
  - focused deep gate -> `59 passed`
  - expanded contract/integration/worker gate -> `119 passed`
  - full coverage gate -> `201 passed`, total coverage `91.73%`
  - module targets met: `auth 98%`, `dependencies 91%`, `routers/trips 85%`, `workers/enrichment_worker 91%`
  - route smoke from `trip_service.main`
  - configured DB `--dry-run` retry
  - ephemeral migrated Postgres `--dry-run`
- Updated `MEMORY/PROJECT_STATE.md` so the active ledger points at `TASK-0046`.

---

## Still Open
- Restore connectivity to the configured `trip-service` database.
- Re-run `uv run python scripts/backfill_trip_status_drift.py --dry-run` against the real target DB.
- If and only if `blocking_rows=[]` and the command exits `0`, run `--apply`.
- Run a second real-DB `--dry-run` and confirm `remaining_counts={}` before any Phase B follow-up is considered.

---

## Blocked
[x] Yes
[ ] No

What is blocking:
The configured target database for `trip-service` is unreachable. `uv run python scripts/backfill_trip_status_drift.py --dry-run` fails with `ConnectionRefusedError` against `127.0.0.1:5433`.

What is needed:
A reachable target DB using the current `trip-service` environment configuration, then a clean `--dry-run`, `--apply`, and verification `--dry-run`.

Who resolves it:
Environment owner / operator with access to the real `trip-service` database.

---

## Risks Found During Build
- The task can be falsely perceived as complete because code validation is green while the real DB rollout gate is still closed.
- Phase B strict cleanup remains unsafe until the real DB backfill sequence finishes cleanly.
- Deep local confidence is now high; the remaining risk is operational, not repo-side.

---

## Unexpected Findings
- The route smoke output currently includes both `/api/v1/trips/{trip_id}/hard` and `/api/v1/trips/{trip_id}/hard-delete`; this task records the current reality and does not reinterpret that alias.
- The configured DB blocker is environmental, not a repo-test failure: the same backfill dry-run succeeds against an ephemeral migrated Postgres instance.
