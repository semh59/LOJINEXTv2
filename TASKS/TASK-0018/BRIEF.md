# BRIEF.md

## Task ID
TASK-0018

## Task Name
Location Service Contract Cleanup

## Phase
Phase 6 - Testing

## Primary Purpose
Remove Location Service import/export ownership and close the remaining contract/runtime drifts without changing Trip Service code.

## Expected Outcome
- `POST /v1/import` and `GET /v1/export` no longer exist in Location Service.
- Location Service only exposes the downstream contracts Trip Service actually uses: route resolve and trip-context.
- Point, pair, processing, and resolve flows return stable `application/problem+json` responses for the identified drift cases.
- Import/export schema baggage is removed with a forward Alembic migration.
- Trip Service files remain untouched.

## In Scope
- `services/location-service/` code, tests, config, migrations, and packaging.
- TASK-0018 records and relevant project memory files.
- Removal of import/export endpoints, logic, schema, env vars, dependencies, and metrics.
- Remediation of the identified Location Service contract/runtime issues.

## Out of Scope
- Any change under `services/trip-service/`.
- Implementing a new Excel/import-export service.
- Reworking smoke topology or excel stubs outside task records.

## Dependencies
- Existing Location Service route resolve and trip-context contracts must stay compatible with Trip Service.
- Current project decisions recorded in `MEMORY/DECISIONS.md`.

## Notes for the Agent
- Worktree already contains unrelated `trip-service` changes; do not touch them.
- Keep `TriggerType.IMPORT_CALCULATE` for historical compatibility even after import/export removal.
