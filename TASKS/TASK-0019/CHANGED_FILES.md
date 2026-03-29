# CHANGED_FILES.md

Every file created or modified for TASK-0019.
Small changes count.

---

## Created
| File | Purpose |
|------|---------|
| `TASKS/TASK-0019/BRIEF.md` | Task definition for the P0/P1 hardening work |
| `TASKS/TASK-0019/PLAN.md` | Locked execution plan for TASK-0019 |
| `TASKS/TASK-0019/STATE.md` | Progress and completion state |
| `TASKS/TASK-0019/CHANGED_FILES.md` | File ledger for the task |
| `TASKS/TASK-0019/TEST_EVIDENCE.md` | Verification evidence |
| `TASKS/TASK-0019/DONE_CHECKLIST.md` | Completion checklist |
| `TASKS/TASK-0019/NEXT_AGENT.md` | Handoff summary |
| `TASKS/TASK-0020/BRIEF.md` | Follow-up shell for deferred P2 cleanup |
| `TASKS/TASK-0020/STATE.md` | Follow-up task state shell |
| `services/location-service/src/location_service/auth.py` | Bearer-token auth helpers for public and internal Location endpoints |
| `services/location-service/src/location_service/routers/removed_endpoints.py` | Exact tombstone for the removed `/v1/pairs/{pair_id}/activate` endpoint |
| `services/location-service/tests/test_auth.py` | Location auth coverage |
| `services/location-service/tests/test_config.py` | Prod fail-fast config coverage |

## Modified
| File | What Changed |
|------|-------------|
| `MEMORY/DECISIONS.md` | Recorded severity-first task split and shared JWT decision |
| `MEMORY/PROJECT_STATE.md` | Registered TASK-0019 as ready for review and TASK-0020 as the next cleanup task |
| `TASKS/TASK-0012/docker-compose.smoke.yml` | Added shared JWT env wiring and live provider passthrough |
| `TASKS/TASK-0012/scripts/smoke.ps1` | Reset the smoke stack, added auth-aware HTTP error handling, fixed test-data drift, and executed authenticated offline/live smoke |
| `services/location-service/.env.example` | Documented `LOCATION_ENVIRONMENT` and Location auth env surface |
| `services/location-service/pyproject.toml` | Added `PyJWT`, removed the conflicting `ulid-py` dependency, and kept `python-ulid` as the single ULID package |
| `services/location-service/uv.lock` | Synced the lockfile to the new dependency set |
| `services/location-service/src/location_service/config.py` | Added environment/auth/provider settings and prod validation |
| `services/location-service/src/location_service/domain/codes.py` | Switched pair-code generation to the stable `python-ulid` API |
| `services/location-service/src/location_service/errors.py` | Added auth/tombstone factories and a global unexpected-exception problem+json handler |
| `services/location-service/src/location_service/main.py` | Gated docs in prod, registered auth and error handlers, and ran startup recovery |
| `services/location-service/src/location_service/middleware.py` | Added reusable `ETag` response support |
| `services/location-service/src/location_service/processing/approval.py` | Returned mutated pairs from shared approve/discard helpers and incremented pair `row_version` |
| `services/location-service/src/location_service/processing/pipeline.py` | Fixed startup recovery, GeoJSON handling, provider metadata, speed-limit extraction, and run timestamps |
| `services/location-service/src/location_service/providers/mapbox_directions.py` | Parsed Mapbox GeoJSON routes and honored config-driven timeout/retry/base URL |
| `services/location-service/src/location_service/providers/mapbox_terrain.py` | Honored config-driven timeout/retry/base URL |
| `services/location-service/src/location_service/providers/ors_validation.py` | Honored config-driven base URL/timeout/retry and skipped network when ORS validation is disabled |
| `services/location-service/src/location_service/routers/approval.py` | Made `/approve` and `/discard` canonical, `If-Match` protected, and `ETag` returning |
| `services/location-service/src/location_service/routers/health.py` | Made readiness truthful with real HTTP `503` semantics |
| `services/location-service/src/location_service/routers/internal_routes.py` | Protected internal endpoints with service auth and surfaced soft-deleted trip-context correctly |
| `services/location-service/src/location_service/routers/pairs.py` | Emitted `ETag`, required `If-Match` on delete, and removed duplicate approval handling |
| `services/location-service/src/location_service/routers/points.py` | Emitted `ETag` on point create/get/update |
| `services/location-service/src/location_service/routers/processing.py` | Kept processing/recovery configuration aligned |
| `services/location-service/tests/conftest.py` | Built auth-aware Location fixtures and test JWT helpers |
| `services/location-service/tests/test_audit_findings.py` | Kept audit-regression tests aligned with auth and removed-endpoint behavior |
| `services/location-service/tests/test_internal_routes.py` | Covered internal service-token auth and soft-deleted trip-context behavior |
| `services/location-service/tests/test_mock_pipeline.py` | Kept mock pipeline fixtures aligned with GeoJSON route objects |
| `services/location-service/tests/test_pairs_api.py` | Covered `ETag`, `If-Match`, canonical approval, and removed `/activate` behavior |
| `services/location-service/tests/test_points_api.py` | Covered point `ETag` behavior |
| `services/location-service/tests/test_processing_flow.py` | Covered startup recovery, pre-migration recovery safety, and updated provider payload shapes |
| `services/location-service/tests/test_providers.py` | Covered GeoJSON parsing and ORS disable/config behavior |
| `services/location-service/tests/test_schema_integration.py` | Covered readiness/docs gating and the global exception handler |
| `services/trip-service/src/trip_service/dependencies.py` | Added Location service JWT auth and business-error mapping |
| `services/trip-service/src/trip_service/workers/enrichment_worker.py` | Marked non-retryable Location business-invalid resolutions as skipped |
| `services/trip-service/tests/test_integration.py` | Covered Location auth headers and business-error mapping |
| `services/trip-service/tests/test_workers.py` | Covered enrichment-worker skip behavior for non-retryable Location failures |

---

## Notes
- `services/trip-service/src/trip_service/config.py`, `services/trip-service/src/trip_service/main.py`, `services/trip-service/src/trip_service/middleware.py`, `services/trip-service/src/trip_service/models.py`, `services/trip-service/src/trip_service/routers/trips.py`, `services/trip-service/src/trip_service/workers/outbox_relay.py`, `services/trip-service/alembic/versions/b2c3d4e5f6a1_add_outbox_claims.py`, `services/trip-service/tests/test_reliability_deep.py`, and `services/trip-service/out.txt` were already dirty outside TASK-0019 and were intentionally not touched.
- Import/export deletions and schema cleanup belong to TASK-0018 and were not re-scoped into TASK-0019.
