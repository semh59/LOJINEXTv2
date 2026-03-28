# PLAN.md

## Objective
Trip-service and its location-service dependency will expose a decision-complete backend contract that matches the locked product rules for Tauri desktop administration and service-driven trip imports.

## How I Understand the Problem
TASK-0010 made the existing V8-shaped trip-service safer, but the product contract changed. The backend still assumes raw `route_id`, header-based admin identity, globally complete slip payloads, and simplistic statuses. The locked product now requires bearer-token auth with `SUPER_ADMIN`, location-pair-driven trip creation, origin/destination snapshots, duration-based overlap blocking, structured Telegram and Excel producer APIs, review reasons, super-admin hard-delete audit, and tighter driver-statement limits. This task must realign the code and tests to that product contract without pretending the Tauri frontend already exists.

## Approach
1. Create TASK-0011 records, register the task in project memory, and lock the file scope before code changes.
2. Redesign trip-service auth, enums, models, schemas, and migrations for roles, trip snapshots, planned duration, review reasons, import source references, reject status, and delete audits.
3. Rework trip-service routers and dependency clients so manual create, edit, approve, reject, empty return, hard delete, Telegram ingest, Telegram fallback ingest, Excel ingest, Excel export feed, overlap validation, and driver statement all follow the locked product contract.
4. Add the location-service trip-context endpoint and wire trip-service to use it for forward and reverse route/duration resolution.
5. Expand automated tests for contract, integration, migration, overlap, audit, and internal service flows; then run lint/tests and record the real evidence.

## Files That Will Change
Nothing outside this list gets touched.
New file needed during build -> update this list first.

| File | Action | Why |
|------|--------|-----|
| `TASKS/TASK-0011/BRIEF.md` | create | Define the new task scope |
| `TASKS/TASK-0011/PLAN.md` | create | Lock the implementation plan |
| `TASKS/TASK-0011/STATE.md` | create | Track progress and risks |
| `TASKS/TASK-0011/CHANGED_FILES.md` | create | Record touched files |
| `TASKS/TASK-0011/TEST_EVIDENCE.md` | create | Capture verification output |
| `TASKS/TASK-0011/NEXT_AGENT.md` | create | Leave a complete handoff |
| `TASKS/TASK-0011/DONE_CHECKLIST.md` | create | Keep repo task template complete |
| `MEMORY/PROJECT_STATE.md` | modify | Register TASK-0011 and increment next task id |
| `MEMORY/DECISIONS.md` | modify | Record new contract and auth decisions |
| `MEMORY/KNOWN_ISSUES.md` | modify | Record any unresolved cross-cutting gaps |
| `services/trip-service/pyproject.toml` | modify | Add auth/runtime dependencies if needed |
| `services/trip-service/.env.example` | modify | Document auth/dependency settings |
| `services/trip-service/uv.lock` | modify | Reflect dependency changes if updated |
| `services/trip-service/alembic/versions/a1b2c3d4e5f6_trip_service_baseline.py` | modify | Extend baseline schema to the new contract |
| `services/trip-service/src/trip_service/config.py` | modify | Add auth and contract config |
| `services/trip-service/src/trip_service/enums.py` | modify | Add roles, sources, statuses, review reasons |
| `services/trip-service/src/trip_service/errors.py` | modify | Add auth, overlap, reject, and delete-audit error codes |
| `services/trip-service/src/trip_service/models.py` | modify | Add snapshot, duration, reference, reject, and audit fields/tables |
| `services/trip-service/src/trip_service/schemas.py` | modify | Replace public request/response contracts |
| `services/trip-service/src/trip_service/middleware.py` | modify | Support auth helpers and tighter date-range validation |
| `services/trip-service/src/trip_service/dependencies.py` | modify | Add location trip-context client helpers |
| `services/trip-service/src/trip_service/timezones.py` | modify | Add range and datetime helpers if required |
| `services/trip-service/src/trip_service/trip_helpers.py` | modify | Centralize overlap and mapping helpers |
| `services/trip-service/src/trip_service/main.py` | modify | Register any new routers/dependencies |
| `services/trip-service/src/trip_service/routers/trips.py` | modify | Rebuild trip flows around the new contract |
| `services/trip-service/src/trip_service/routers/driver_statement.py` | modify | Enforce 31-day range and product visibility rules |
| `services/trip-service/src/trip_service/routers/health.py` | modify | Keep readiness aligned with new auth/client surface if needed |
| `services/trip-service/src/trip_service/auth.py` | create | Bearer-token parsing and role enforcement |
| `services/trip-service/tests/conftest.py` | modify | Provide auth token fixtures and dependency stubs |
| `services/trip-service/tests/test_contract.py` | modify | Cover public auth and contract changes |
| `services/trip-service/tests/test_integration.py` | modify | Cover create/edit/approve/reject/delete/import flows |
| `services/trip-service/tests/test_unit.py` | modify | Cover mapping, overlap, and review helper logic |
| `services/trip-service/tests/test_migrations.py` | modify | Verify new schema columns, indexes, and audit table |
| `services/trip-service/tests/test_workers.py` | modify | Keep worker expectations aligned with new states if affected |
| `services/trip-service/tests/test_repo_cleanliness.py` | modify | Keep cleanliness checks aligned with the new source types/contracts |
| `services/location-service/src/location_service/schemas.py` | modify | Add trip-context response schema |
| `services/location-service/src/location_service/errors.py` | modify | Add trip-context not-found/inactive errors if needed |
| `services/location-service/src/location_service/main.py` | modify | Register the new trip-context router |
| `services/location-service/src/location_service/routers/internal_routes.py` | modify | Add the trip-context endpoint beside resolve |
| `services/location-service/tests/conftest.py` | modify | Expose the updated internal routes router |
| `services/location-service/tests/test_internal_routes.py` | modify | Cover trip-context and existing resolve behavior |

## Risks
- This task changes the trip-service public contract significantly; tests and helper fixtures can break widely until updated together.
- The repo still has unrelated dirty changes; edits must avoid disturbing out-of-scope files.
- Overlap blocking depends on location-service duration data and can expose hidden fixture assumptions.
- Introducing bearer-token auth without a real identity provider in-repo requires deterministic test-only token handling.
- Changing the baseline migration means every schema-sensitive test must stay aligned with Alembic.

## Test Cases
- test that manual create requires bearer auth and rejects legacy header-only requests in prod mode
- test that admin manual create with `route_pair_id` snapshots origin/destination and planned duration
- test that manual create without `vehicle_id` returns `422`
- test that normal admin cannot create future trips
- test that super admin future manual trips become `PENDING_REVIEW`
- test that empty return derives reverse route/duration and uses the `-B` suffix
- test that empty return is blocked when the base trip is not `COMPLETED`
- test that Telegram fallback ingest creates an incomplete `PENDING_REVIEW` record with `FALLBACK_MINIMAL`
- test that Excel ingest requires complete rows and rejects duplicates by `source_reference_key`
- test that overlap conflicts return stable `409` codes for driver, vehicle, and trailer
- test that imported-trip driver changes are blocked for admin and allowed for super admin with `change_reason`
- test that reject transitions `PENDING_REVIEW` to `REJECTED`
- test that hard delete requires `SUPER_ADMIN`, `reason`, and prior `SOFT_DELETED`
- test that hard delete persists the immutable audit snapshot before removing the trip
- test that driver statement rejects date ranges longer than `31` days
- test that location-service trip-context returns forward and reverse route/duration for active pairs

## Out of Scope
- Tauri desktop application code or packaging
- Telegram PDF rendering or delivery
- Excel file generation and parsing outside the structured service contract
- Fleet-service server work outside this repository

## Completion Criterion
- Trip-service public and internal endpoints match the locked product contract with automated coverage.
- Location-service exposes both route resolve and trip-context endpoints required by trip-service.
- Alembic-backed tests prove the new schema, overlap rules, auth rules, and delete audit behavior.
- Task and project memory files truthfully describe the work, remaining risks, and verification output.

---

## Plan Revisions
Document every change to this plan. Do not silently deviate.
