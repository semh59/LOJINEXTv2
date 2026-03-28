# PLAN — TASK-0017

## Objective
Remove remaining Trip Service risks by changing outbox publish flow to avoid duplicate publishes, fixing smoke script exit behavior, and validating release-gate tests.

## How I Understand the Problem
Outbox relay currently publishes before commit and can duplicate if commit fails. Smoke script can return non-zero due to PowerShell error stream behavior. We must fix both and keep the test suite green.

## Approach
1. Implement outbox publish flow that avoids duplicate publishes (introduce PUBLISHING state and publish gating).
2. Update outbox relay selection and status transitions; adjust observability if needed.
3. Update smoke script to avoid NativeCommandError and ensure exit 0 on successful steps.
4. Add/adjust tests for new outbox behavior and smoke script expectations.
5. Update DECISIONS to supersede prior outbox acceptance.
6. Run Trip Service pytest and smoke script; capture evidence.
7. Update task records and handoff.

## Files That Will Change
- `services/trip-service/src/trip_service/enums.py`
- `services/trip-service/src/trip_service/routers/trips.py`
- `services/trip-service/src/trip_service/workers/outbox_relay.py`
- `services/trip-service/tests/test_workers.py`
- `TASKS/TASK-0012/scripts/smoke.ps1`
- `MEMORY/DECISIONS.md`
- `TASKS/TASK-0017/STATE.md`
- `TASKS/TASK-0017/CHANGED_FILES.md`
- `TASKS/TASK-0017/TEST_EVIDENCE.md`
- `TASKS/TASK-0017/DONE_CHECKLIST.md`
- `TASKS/TASK-0017/NEXT_AGENT.md`
- `MEMORY/PROJECT_STATE.md`

## Risks
- Switching outbox state machine may cause stuck PUBLISHING rows if commit fails after publish.
- Smoke script changes must not mask real errors; use exit code check.

## Test Cases
1. Relay ignores non-ready rows and does not republish PUBLISHING rows.
2. Relay marks rows PUBLISHING before publish and PUBLISHED after successful publish.
3. Smoke script exits 0 on successful completion.
4. Trip Service pytest passes.

## Out of Scope
- Kafka transactional publishing.

## Completion Criterion
- Outbox duplicate risk removed per new flow.
- Smoke script exits 0 on success.
- Tests pass with evidence recorded.
