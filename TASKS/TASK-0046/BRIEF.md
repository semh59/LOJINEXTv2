# BRIEF.md

## Task ID
TASK-0046

## Task Name
Trip-Service Phase A Repair Handoff and Backfill Gate

## Phase
Phase 7 - Production Recovery

## Primary Purpose
Record the already-landed trip-service Phase A repair truthfully and gate any later strict cleanup behind a successful real-database backfill run.

## Expected Outcome
- `TASKS/TASK-0046/` contains a complete handoff for the landed `trip-service` Phase A patch.
- `MEMORY/PROJECT_STATE.md` shows `TASK-0046` as the active follow-up and advances `Next Task ID` to `TASK-0047`.
- `TEST_EVIDENCE.md` records the exact lint, test, route smoke, configured DB dry-run, and ephemeral migrated Postgres dry-run outputs.
- `STATE.md` shows that target DB `--dry-run`, `--apply`, and verification remain blocked until the configured database is reachable.
- `NEXT_AGENT.md` gives the exact backfill order and stop conditions for real DB execution.

## In Scope
- Create the full `TASKS/TASK-0046/` record set for the trip-service Phase A repair.
- Record the exact Phase A patch file set and current public contract facts for `trip-service`.
- Capture current validation evidence, including the failed configured DB dry-run and the successful ephemeral migrated Postgres dry-run.
- Update `MEMORY/PROJECT_STATE.md` so the active-task ledger matches the current follow-up state.

## Out of Scope
- New `trip-service` source changes
- Phase B strict cleanup
- Any code changes outside `trip-service`
- Applying the backfill to a real database without a reachable configured DB

## Dependencies
- `TASKS/TASK-0045/`
- `MEMORY/DECISIONS.md`
- `MEMORY/KNOWN_ISSUES.md`
- Existing `trip-service` Phase A patch and test suite

## Notes for the Agent
- `TASK-0045` stays intact; do not fold this follow-up back into the cross-service recovery task.
- This task records a real blocker: `uv run python scripts/backfill_trip_status_drift.py --dry-run` against the configured DB currently fails because the target database refuses connections.
- Phase B strict cleanup is not allowed until a real DB `--dry-run`, `--apply`, and verification `--dry-run` all succeed.
