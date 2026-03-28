# NEXT_AGENT.md

## What is this task trying to achieve?
Produce a Trip Service-only release-hardening audit with evidence-based findings and a readiness decision.

## What was done this session?
- Audited idempotency flow, outbox relay, production config defaults, and tests.
- Wrote `TRIP_SERVICE_RELEASE_HARDENING_REPORT.md` with PASS/FAIL results and checklist.
- Updated project state and task records.

## What is not done yet?
- Finalize task status to `ready_for_review` or `done` once you confirm the report is acceptable.

## What is the riskiest thing the next agent must know?
- Release decision is NOT READY due to idempotency in-flight 5xx, outbox duplicate window, and missing prod fail-fast validation/tests.

## What is the very first action to take?
Review `TASKS/TASK-0015/TRIP_SERVICE_RELEASE_HARDENING_REPORT.md` and confirm findings.

## Which files are critical to read beyond the standard list?
- `TASKS/TASK-0015/TRIP_SERVICE_RELEASE_HARDENING_REPORT.md`
- `services/trip-service/src/trip_service/routers/trips.py`
- `services/trip-service/src/trip_service/workers/outbox_relay.py`
- `services/trip-service/src/trip_service/config.py`
- `services/trip-service/tests/test_integration.py`
- `services/trip-service/tests/test_workers.py`

## Are there traps or non-obvious things?
- Findings are based on static inspection; concurrency behaviors are inferred from code paths.

## Are there open decisions that need a human?
- Whether to accept at-least-once outbox duplicate risk or implement mitigation.

## What does done look like for the remaining work?
- Task state marked `ready_for_review`/`done` and checklist updated as appropriate.

## What temporary implementations were introduced and where?
- None.
