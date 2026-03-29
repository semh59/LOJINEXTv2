# PLAN.md

## Objective
Location Service will be safe to expose as a production route authority by fixing its live provider/runtime failures, enforcing auth and readiness semantics, completing ETag/concurrency behavior, and aligning Trip Service's dependency handling to the corrected contract.

## How I Understand the Problem
TASK-0018 narrowed Location Service but left release-blocking gaps: live Mapbox route parsing is still broken, auth is missing, readiness lies via HTTP 200, provider config is partly dead, approval lifecycle is ambiguous, ETag handling is incomplete, and Trip Service still treats several Location business responses as dependency outages. This task fixes only those P0/P1 issues and explicitly leaves P2 cleanup for TASK-0020.

## Approach
1. Bootstrap TASK-0019 records and update project memory for the new active task and the deferred TASK-0020 cleanup follow-up.
2. Add Location Service auth and prod fail-fast config validation, gate docs in prod, and make readiness/status handling truthful.
3. Close the Location error and concurrency surface by adding a global exception handler, ETag response headers, If-Match checks on pair state mutations, and a single approval contract with a tombstone for `/activate`.
4. Fix live provider/runtime behavior: Mapbox geometry parsing, provider config wiring, ORS disable behavior, and processing-run startup recovery.
5. Update Trip Service's Location client/auth/error mapping and worker behavior so business-invalid responses are not treated as outages.
6. Update the smoke harness for authenticated offline and live flows.
7. Add or update tests, run lint/pytest/Alembic/smoke verification, and record the actual evidence.

## Files That Will Change
Nothing outside this list gets touched.

| File | Action | Why |
|------|--------|-----|
| `MEMORY/DECISIONS.md` | modify | Record Location auth/shared-JWT and severity-first follow-up decisions |
| `MEMORY/PROJECT_STATE.md` | modify | Register TASK-0019 and reserve TASK-0020 as the next cleanup task |
| `TASKS/TASK-0019/BRIEF.md` | modify | Task definition |
| `TASKS/TASK-0019/PLAN.md` | modify | Execution plan |
| `TASKS/TASK-0019/STATE.md` | modify | Progress tracking |
| `TASKS/TASK-0019/CHANGED_FILES.md` | create | Final file ledger |
| `TASKS/TASK-0019/TEST_EVIDENCE.md` | create | Final test evidence |
| `TASKS/TASK-0019/NEXT_AGENT.md` | create | Final handoff |
| `TASKS/TASK-0019/DONE_CHECKLIST.md` | create | Final completion record |
| `services/location-service/pyproject.toml` | modify | Add JWT dependency |
| `services/location-service/uv.lock` | modify | Sync dependency lockfile |
| `services/location-service/.env.example` | modify | Document auth and environment surface |
| `services/location-service/src/location_service/config.py` | modify | Add environment/auth settings and prod validation |
| `services/location-service/src/location_service/main.py` | modify | Gate docs, register handlers, run startup recovery |
| `services/location-service/src/location_service/errors.py` | modify | Add global exception handling and removed-endpoint error |
| `services/location-service/src/location_service/middleware.py` | modify | Add ETag response helper |
| `services/location-service/src/location_service/auth.py` | create | Bearer-token auth helpers for public/internal endpoints |
| `services/location-service/src/location_service/routers/health.py` | modify | Return truthful readiness status codes |
| `services/location-service/src/location_service/routers/points.py` | modify | Emit ETag headers |
| `services/location-service/src/location_service/routers/pairs.py` | modify | Require If-Match on delete/approve, emit ETag, remove duplicate approval implementation |
| `services/location-service/src/location_service/routers/approval.py` | modify | Make approve/discard canonical and return PairResponse |
| `services/location-service/src/location_service/routers/internal_routes.py` | modify | Protect internal routes with service auth |
| `services/location-service/src/location_service/routers/processing.py` | modify | Keep processing semantics aligned with recovery changes |
| `services/location-service/src/location_service/routers/removed_endpoints.py` | create | Exact 404 tombstone for `/activate` |
| `services/location-service/src/location_service/processing/approval.py` | modify | Support router-level ETag checks using shared session-capable approval/discard helpers |
| `services/location-service/src/location_service/processing/pipeline.py` | modify | Fix Mapbox parsing, provider config use, run timestamps, and startup recovery |
| `services/location-service/src/location_service/providers/mapbox_directions.py` | modify | Parse GeoJSON geometry and use config-driven timeout/retry/base URL |
| `services/location-service/src/location_service/providers/mapbox_terrain.py` | modify | Use config-driven timeout/retry/base URL |
| `services/location-service/src/location_service/providers/ors_validation.py` | modify | Use config-driven base URL/timeout and skip network when disabled |
| `services/location-service/tests/conftest.py` | modify | Build auth-aware app/client fixtures |
| `services/location-service/tests/test_points_api.py` | modify | Cover ETag behavior |
| `services/location-service/tests/test_pairs_api.py` | modify | Cover auth, ETag, If-Match, and approval tombstone behavior |
| `services/location-service/tests/test_internal_routes.py` | modify | Cover service-token auth |
| `services/location-service/tests/test_processing_flow.py` | modify | Cover startup recovery and updated provider objects |
| `services/location-service/tests/test_mock_pipeline.py` | modify | Keep mock pipeline tests aligned with the GeoJSON provider contract |
| `services/location-service/tests/test_providers.py` | modify | Cover GeoJSON parsing and ORS disable/config use |
| `services/location-service/tests/test_schema_integration.py` | modify | Cover readiness/docs gating |
| `services/location-service/tests/test_auth.py` | create | Cover public/internal auth behavior |
| `services/location-service/tests/test_config.py` | create | Cover prod fail-fast validation |
| `services/trip-service/src/trip_service/dependencies.py` | modify | Add Location service JWT auth and business-error mapping |
| `services/trip-service/src/trip_service/workers/enrichment_worker.py` | modify | Avoid retrying non-retryable Location business failures |
| `services/trip-service/src/trip_service/routers/health.py` | modify | Probe Location with auth |
| `services/trip-service/tests/test_integration.py` | modify | Cover dependency mapping |
| `services/trip-service/tests/test_workers.py` | modify | Cover enrichment worker business-invalid handling |
| `TASKS/TASK-0012/docker-compose.smoke.yml` | modify | Pass Location auth and optional live-provider envs |
| `TASKS/TASK-0012/scripts/smoke.ps1` | modify | Support authenticated offline and live smoke runs |

## Risks
- Location auth changes touch every endpoint and every test fixture; a partial rollout will create many false failures.
- Startup run recovery must only reclaim safe queued/stale runs; reclaiming healthy active work would create duplicate processing.
- Live smoke depends on local provider secrets and external network availability; this must be recorded honestly if unavailable.
- Existing unrelated `trip-service` worktree changes must remain untouched unless they overlap the specific files listed above.

## Test Cases
1. Test that Location public endpoints reject missing or wrong-role bearer tokens with 401/403, while health/readiness stay open.
2. Test that Location internal endpoints reject non-service callers and accept `service=trip-service` bearer tokens.
3. Test that prod Location config fails on default JWT secret, default DB URL, or missing provider secrets when required.
4. Test that `/ready` returns 503 when required dependencies/config are missing.
5. Test that point and pair detail/mutation responses emit `ETag` and pair delete/approve/discard require `If-Match`.
6. Test that `/v1/pairs/{pair_id}/activate` returns an exact removed-endpoint 404.
7. Test that Mapbox GeoJSON route responses parse correctly and ORS does not call the network when disabled.
8. Test that queued and stale running processing runs are reclaimed at startup.
9. Test that Trip Service maps `LOCATION_ROUTE_RESOLUTION_NOT_FOUND`, `ROUTE_AMBIGUOUS`, and inactive trip-context responses to validation errors rather than dependency unavailable.
10. Test that the enrichment worker marks non-retryable route resolution failures as skipped instead of retrying.
11. Run `uv run --directory services/location-service --extra dev ruff check src tests`.
12. Run `uv run --directory services/location-service --extra dev pytest`.
13. Run `uv run --directory services/trip-service --extra dev pytest`.
14. Run `uv run --directory services/location-service alembic upgrade head`.
15. Run the offline smoke stack.
16. Run the live provider smoke stack if provider keys are available.

## Out of Scope
- Dead table/model/error cleanup from TASK-0020.
- Persistent worker redesign.
- Full observability rewiring and metrics cleanup.
- Error taxonomy normalization beyond what is required for the new auth/tombstone behavior.

## Completion Criterion
- Live Mapbox route parsing is fixed and verified.
- Location Service non-health endpoints require auth and prod docs are gated.
- Readiness uses correct HTTP status semantics.
- Pair approval lifecycle is unambiguous and ETag/If-Match behavior is complete for the targeted paths.
- Trip Service authenticates to Location Service and classifies Location business failures correctly.
- Offline smoke passes, and live smoke is either passing or documented with exact failure evidence.

## Plan Revisions
None yet.
