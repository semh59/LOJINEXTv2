# BRIEF.md

## Task ID
TASK-0023

## Task Name
Location Service Critical Fixes + Retest

## Phase
Phase 6 - Testing

## Primary Purpose
Fix all identified location-service issues (treated as critical) and re-run the full prod-hard test matrix with clean evidence.

## Expected Outcome
- Pair code generation no longer raises at runtime.
- Load/soak completes without internal resolve 404.
- Pytest runs without PYTHONPATH hacks.
- Alembic upgrade succeeds on a clean DB (using docker if needed).
- Smoke script no longer emits misleading NativeCommandError noise.
- Full test evidence captured in TASKS/TASK-0023/TEST_EVIDENCE.md.

## In Scope
- Code fixes in location-service and load test script.
- Test configuration updates for pytest.
- Smoke script log/noise improvements.
- Rerun test matrix and capture evidence.

## Out of Scope
- Public or internal contract changes.
- Feature development beyond fixes above.

## Dependencies
- Docker + Docker Compose available.
- Live provider keys available for smoke.

## Notes for the Agent
- Follow AGENTS.md workflow and record all evidence.
- Do not change API contracts.
