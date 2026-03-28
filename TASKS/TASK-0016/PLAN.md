# PLAN — TASK-0016

## Objective
Harden Trip Service for production by fixing idempotency in-flight behavior, enforcing prod fail-fast config validation, adding release-gate tests, and documenting outbox at-least-once semantics.

## How I Understand the Problem
Trip Service currently returns 5xx for in-flight idempotency, lacks prod fail-fast config validation, and misses required release-gate tests. Outbox duplicate-publish risk is a known distributed-systems tradeoff that must be explicitly documented as accepted.

## Approach
1. Add new Problem Detail error for idempotency in-flight conflicts.
2. Update idempotency handling to return controlled 409 (no 5xx) when a record is incomplete.
3. Add prod validation in config and call it during app startup.
4. Add release-gate tests (idempotency in-flight, payload mismatch, enrichment reclaim, create›outbox).
5. Document outbox duplicate-publish acceptance in MEMORY/DECISIONS.md.
6. Run Trip Service tests and record evidence.
7. Update task records and handoff.

## Files That Will Change
- `services/trip-service/src/trip_service/routers/trips.py`
- `services/trip-service/src/trip_service/errors.py`
- `services/trip-service/src/trip_service/config.py`
- `services/trip-service/src/trip_service/main.py`
- `services/trip-service/tests/test_integration.py`
- `services/trip-service/tests/test_workers.py`
- `services/trip-service/tests/test_unit.py` or `services/trip-service/tests/test_config.py`
- `MEMORY/DECISIONS.md`
- `TASKS/TASK-0016/STATE.md`
- `TASKS/TASK-0016/CHANGED_FILES.md`
- `TASKS/TASK-0016/TEST_EVIDENCE.md`
- `TASKS/TASK-0016/DONE_CHECKLIST.md`
- `TASKS/TASK-0016/NEXT_AGENT.md`

## Risks
- Parallel idempotency test may be sensitive to transaction isolation; use deterministic pre-inserted incomplete record to avoid flakiness.
- Prod validation may break local dev if environment is misconfigured; ensure dev/test unaffected.

## Test Cases
1. Incomplete idempotency record returns 409 with `TRIP_IDEMPOTENCY_IN_FLIGHT`.
2. Same Idempotency-Key with payload mismatch returns 409 with `TRIP_IDEMPOTENCY_PAYLOAD_MISMATCH`.
3. Prod settings validation fails on default JWT secret.
4. Prod settings validation fails on default DB URL.
5. Prod settings validation fails on PLAINTEXT Kafka unless explicitly allowed.
6. Enrichment worker reclaims stale claims.
7. Create › outbox row exists.

## Out of Scope
- Outbox publish/commit mitigation (documented acceptance only).

## Completion Criterion
- All code changes merged and tests pass with evidence recorded.
- Documentation entry added for outbox risk acceptance.
