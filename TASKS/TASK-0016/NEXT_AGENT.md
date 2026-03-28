# NEXT_AGENT.md

## What is this task trying to achieve?
Implement Trip Service hardening fixes for idempotency, prod config validation, release-gate tests, and document outbox at-least-once acceptance.

## What was done this session?
- Added idempotency in-flight conflict error and logic update.
- Added prod fail-fast validation and startup hook.
- Added tests for idempotency, outbox row creation, and stale-claim reclaim.
- Added config validation tests.
- Documented outbox duplicate-publish acceptance in `MEMORY/DECISIONS.md`.
- Ran trip-service pytest and captured evidence.

## What is not done yet?
- Finalize task status to `ready_for_review` or `done` after confirming records.
- Complete DONE_CHECKLIST and CHANGED_FILES verification if needed.

## What is the riskiest thing the next agent must know?
- Prod validation now fails fast for default secrets/URLs; deployments must set required env vars.

## What is the very first action to take?
Review `TASKS/TASK-0016/STATE.md` and `TASKS/TASK-0016/TEST_EVIDENCE.md`, then mark task ready for review/done.

## Which files are critical to read beyond the standard list?
- `services/trip-service/src/trip_service/routers/trips.py`
- `services/trip-service/src/trip_service/config.py`
- `services/trip-service/src/trip_service/main.py`
- `services/trip-service/tests/test_integration.py`
- `services/trip-service/tests/test_workers.py`
- `services/trip-service/tests/test_config.py`
- `MEMORY/DECISIONS.md`

## Are there traps or non-obvious things?
- Idempotency in-flight test uses a pre-inserted incomplete record instead of true parallelism for deterministic behavior.

## Are there open decisions that need a human?
- None.

## What does done look like for the remaining work?
- Task marked `ready_for_review`/`done` with updated checklist and records.

## What temporary implementations were introduced and where?
- None.
