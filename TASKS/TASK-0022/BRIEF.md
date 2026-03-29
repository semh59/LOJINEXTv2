# BRIEF.md

## Task ID
TASK-0022

## Task Name
Location Service Deep Audit + Prod-Hard Tests

## Phase
Phase 6 - Testing

## Primary Purpose
Produce a location-service-only audit and prod-hard test evidence focused on API/endpoint behavior, database/migrations, and public/internal contract alignment.

## Expected Outcome
- Line-by-line audit findings recorded in TASKS/TASK-0022/AUDIT_REPORT.md.
- Full test evidence recorded in TASKS/TASK-0022/TEST_EVIDENCE.md for lint, pytest, alembic upgrade, docker smoke (live providers), and load/soak run.
- No code or contract changes introduced; only findings and evidence.

## In Scope
- Audit all location-service source and test files with emphasis on routers, schemas, auth, query contracts, errors, models, and migrations.
- Run prod-hard test matrix for location-service only, including live provider smoke and a new load/soak script.
- Record findings and evidence in TASK-0022 artifacts.

## Out of Scope
- Any code changes to location-service behavior or contract.
- Trip-service audits or tests.
- Cleanup/architecture work tracked in TASK-0020.

## Dependencies
- Docker + Docker Compose installed.
- Live provider keys present in services/location-service/.env for smoke.
- Local postgres availability for alembic upgrade.

## Notes for the Agent
- Follow AGENTS.md workflow and record all evidence.
- If findings require code changes, open a new task rather than fixing here.
