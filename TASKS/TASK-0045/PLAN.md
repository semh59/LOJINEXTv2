# PLAN.md

## Objective
After this task, repository memory will match the real repo state and the live Trip/Fleet/Driver contract baseline will be repaired, authenticated, and regression-tested.

## How I Understand the Problem
The repo currently claims a more complete production state than the code actually provides. The biggest immediate blockers are not abstract architecture gaps; they are concrete broken service boundaries: Trip calls Fleet without auth and expects the wrong response shape, Fleet calls Driver and Trip endpoints that do not exist, Driver signs Trip-bound tokens with an incompatible role/secret model, and Driver readiness still reports success too easily. Those issues must be corrected before wider runtime promotion or shared-auth package work is safe.

The requested long recovery roadmap is larger than one repo task. This task implements the smallest coherent first slice: repo truth plus the live Trip/Fleet/Driver contract repair needed to establish a trustworthy baseline.

## Approach
1. Create `TASK-0045` records and update `MEMORY/PROJECT_STATE.md` so the repo truth matches the actual task ledger before changing service code.
2. Repair `trip-service` internal reference checks and outbound Fleet calls by fixing the broken driver-check status logic, adding a generic asset-reference endpoint, sending service auth to Fleet, and making Fleet response parsing compatible during the transition.
3. Repair `fleet-service` live dependencies by switching Driver validation to the real eligibility endpoint, allowing nullable vehicle/trailer trip-compat requests, returning Trip-compatible validation fields, and wiring Trip reference checks into hard-delete flows.
4. Repair `driver-service` live dependency/auth behavior by generating Trip-bound `SERVICE` tokens, accepting a shared HS256 bridge, and making `/ready` fail on stale or missing worker heartbeats.
5. Run targeted tests for Trip, Fleet, and Driver recovery paths, then update task records, memory, and handoff files with exact evidence and remaining follow-up work.

## Files That Will Change
Nothing outside this list gets touched.
New file needed during build -> update this list first.

| File | Action | Why |
|------|--------|-----|
| `MEMORY/PROJECT_STATE.md` | modify | Align project/task memory with the actual repo state and register TASK-0045 |
| `MEMORY/DECISIONS.md` | modify | Record any recovery-time auth/contract decision introduced by this task |
| `MEMORY/KNOWN_ISSUES.md` | modify | Record any cross-cutting issue discovered but not fully resolved |
| `TASKS/TASK-0045/BRIEF.md` | create | Task definition |
| `TASKS/TASK-0045/PLAN.md` | create | Task plan |
| `TASKS/TASK-0045/STATE.md` | create | Progress ledger |
| `TASKS/TASK-0045/CHANGED_FILES.md` | create | File ledger |
| `TASKS/TASK-0045/TEST_EVIDENCE.md` | create | Test evidence |
| `TASKS/TASK-0045/NEXT_AGENT.md` | create | Handoff notes |
| `TASKS/TASK-0045/DONE_CHECKLIST.md` | create | Completion checklist |
| `services/trip-service/src/trip_service/config.py` | modify | Support recovery-time shared auth bridge if introduced |
| `services/trip-service/src/trip_service/auth.py` | modify | Use the resolved auth secret for inbound service verification |
| `services/trip-service/src/trip_service/dependencies.py` | modify | Add Fleet auth headers and compatibility parsing |
| `services/trip-service/src/trip_service/schemas.py` | modify | Add request/response models for generic asset reference checks |
| `services/trip-service/src/trip_service/routers/trips.py` | modify | Fix driver reference check and add generic asset reference endpoint |
| `services/trip-service/tests/test_contract.py` | modify | Cover internal auth and new reference-check contract expectations |
| `services/trip-service/tests/test_integration.py` | modify | Cover Fleet auth headers and compatibility parsing |
| `services/fleet-service/src/fleet_service/config.py` | modify | Support recovery-time shared auth bridge resolution |
| `services/fleet-service/src/fleet_service/auth.py` | modify | Use the resolved auth secret for inbound/outbound service JWTs |
| `services/fleet-service/src/fleet_service/clients/driver_client.py` | modify | Use the real Driver eligibility contract |
| `services/fleet-service/src/fleet_service/clients/trip_client.py` | modify | Use the new Trip asset reference endpoint |
| `services/fleet-service/src/fleet_service/schemas/requests.py` | modify | Allow nullable vehicle/trailer inputs for trip compatibility |
| `services/fleet-service/src/fleet_service/timestamps.py` | create | Centralize naive UTC timestamp normalization for the current Fleet schema |
| `services/fleet-service/src/fleet_service/repositories/idempotency_repo.py` | modify | Make TTL comparisons use naive UTC timestamps that match the Fleet schema |
| `services/fleet-service/src/fleet_service/repositories/outbox_repo.py` | modify | Make outbox claim/publish timestamps use naive UTC timestamps that match the Fleet schema |
| `services/fleet-service/src/fleet_service/services/internal_service.py` | modify | Return Trip-compatible validation fields and truthful dependency behavior |
| `services/fleet-service/src/fleet_service/services/vehicle_service.py` | modify | Normalize vehicle-domain timestamps so create/update/delete flows work with the current Fleet schema |
| `services/fleet-service/src/fleet_service/services/trailer_service.py` | modify | Normalize trailer-domain timestamps so create/update/delete flows work with the current Fleet schema |
| `services/fleet-service/src/fleet_service/services/vehicle_spec_service.py` | modify | Normalize spec-version timestamps and effective-from inputs for the current Fleet schema |
| `services/fleet-service/src/fleet_service/worker_heartbeats.py` | modify | Normalize fleet worker heartbeat timestamps so readiness and tests do not fail on naive/aware UTC mismatches |
| `services/fleet-service/src/fleet_service/workers/outbox_relay.py` | modify | Make relay retry scheduling and publish finalization use the Fleet schema's naive UTC timestamps |
| `services/fleet-service/src/fleet_service/entrypoints/worker.py` | modify | Make worker cleanup timestamps use the Fleet schema's naive UTC timestamps |
| `services/fleet-service/src/fleet_service/routers/vehicle_router.py` | modify | Wire Trip reference checks into vehicle hard-delete |
| `services/fleet-service/src/fleet_service/routers/trailer_router.py` | modify | Wire Trip reference checks into trailer hard-delete |
| `services/fleet-service/tests/conftest.py` | modify | Replace stale dependency monkeypatches so targeted recovery tests can run |
| `services/fleet-service/tests/contract/test_internal_contracts.py` | modify | Cover repaired internal validation contract behavior |
| `services/fleet-service/pyproject.toml` | modify | Make targeted pytest runs resolve the local `src/` package path directly from the service root |
| `services/driver-service/src/driver_service/config.py` | modify | Support recovery-time shared auth bridge resolution |
| `services/driver-service/src/driver_service/auth.py` | modify | Emit Trip-bound `SERVICE` tokens and enforce internal-service allowlists |
| `services/driver-service/src/driver_service/routers/__init__.py` | modify | Make readiness fail on stale or missing worker heartbeats |
| `services/driver-service/src/driver_service/routers/maintenance.py` | modify | Use the repaired Trip reference contract and shared auth bridge |
| `services/driver-service/tests/test_contract.py` | modify | Cover Trip client contract and service-token generation behavior |
| `services/driver-service/tests/test_smoke.py` | modify | Cover truthful readiness behavior |
| `services/driver-service/pyproject.toml` | modify | Make targeted pytest runs resolve the local `src/` package path directly from the service root |
| `services/trip-service/.env.example` | modify | Document any recovery-time shared auth env surface |
| `services/fleet-service/.env.example` | modify | Document any recovery-time shared auth env surface |
| `services/driver-service/.env.example` | modify | Document any recovery-time shared auth env surface |

## Risks
- The services currently use different default JWT secrets; a shared-secret bridge must not silently break existing single-service tests.
- Fleet tests are already stale in multiple places; touching too much of that matrix could expand the task past the live-contract slice.
- Driver tests override auth dependencies heavily, so direct router coverage can hide auth regressions unless explicit auth-unit coverage is added.
- Tightening readiness without matching worker heartbeat names or timing could make `/ready` fail constantly.

## Test Cases
- Test that `GET /internal/v1/trips/driver-check/{driver_id}` no longer crashes and reports `active_trip_count` correctly.
- Test that `POST /internal/v1/assets/reference-check` returns the correct shape for `DRIVER`, `VEHICLE`, and `TRAILER`.
- Test that Trip sends a bearer token to Fleet validation and accepts both legacy and repaired Fleet response fields.
- Test that Fleet trip-reference validation accepts `vehicle_id=null` and returns `driver_valid`, `vehicle_valid`, `trailer_valid`, `errors`, and `warnings`.
- Test that Fleet hard-delete paths invoke the Trip reference checker.
- Test that Driver maintenance Trip checks use a `SERVICE` role token and the repaired Trip endpoint contract.
- Test that Driver `/ready` returns `503` when worker heartbeats are missing or stale.

## Out of Scope
- Shared auth package extraction
- RS256/JWKS migration
- Full Fleet suite repair
- Compose, proxy, metrics, and workflow promotion work
- Location Service contract or ownership changes

## Completion Criterion
The task is complete when repo memory truth is updated, the repaired Trip/Fleet/Driver contract paths are implemented with targeted automated coverage, and `TASK-0045` records contain exact test evidence plus remaining follow-up risks.

---

## Plan Revisions
Document every change to this plan. Do not silently deviate.

- 2026-04-05: Added `services/fleet-service/pyproject.toml` and `services/driver-service/pyproject.toml` after targeted test runs showed that `python -m pytest ...` from the service roots could not import the local `src/` packages. This is a test-bootstrap repair required to prove the recovery slice.
- 2026-04-05: Added `services/fleet-service/src/fleet_service/worker_heartbeats.py` after the targeted Fleet test run exposed a real naive/aware UTC mismatch in the heartbeat helper used by readiness and worker loops.
- 2026-04-05: Expanded the Fleet file list with a shared timestamp helper plus the request, repository, and worker paths that still wrote timezone-aware UTC values into a schema that stores naive UTC timestamps. The targeted contract tests showed this is a real runtime bug, not just a test fixture issue.
