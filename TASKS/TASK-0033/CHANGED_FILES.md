# CHANGED_FILES.md

Every file created, modified, or deleted this session.
Small changes count.

---

## Created
| File | Purpose |
|------|---------|
| `TASKS/TASK-0033/BRIEF.md` | Define TASK-0033 scope and success conditions |
| `TASKS/TASK-0033/PLAN.md` | Record execution plan |
| `TASKS/TASK-0033/STATE.md` | Track task status and completion |
| `TASKS/TASK-0033/CHANGED_FILES.md` | Track touched files |
| `TASKS/TASK-0033/TEST_EVIDENCE.md` | Record automated verification evidence |
| `TASKS/TASK-0033/NEXT_AGENT.md` | Capture completion and follow-up notes |
| `TASKS/TASK-0033/DONE_CHECKLIST.md` | Record completion checklist status |
| `services/trip-service/src/trip_service/http_clients.py` | Shared long-lived HTTP clients for dependency and worker calls |
| `services/location-service/src/location_service/provider_health.py` | TTL-cached live provider probe support for readiness |
| `services/location-service/alembic/versions/4d2b8c9e7f10_route_pair_live_uniqueness.py` | Route pair live uniqueness migration |
| `services/location-service/tests/test_migrations.py` | Alembic regression coverage for Location Service |

## Modified
| File | What Changed |
|------|-------------|
| `MEMORY/PROJECT_STATE.md` | Registered TASK-0033 as active/remediated work |
| `MEMORY/DECISIONS.md` | Recorded TASK-0033 scope split and remediation defaults |
| `services/trip-service/src/trip_service/models.py` | Added `TripOutbox.last_error_code` ORM field |
| `services/trip-service/src/trip_service/trip_helpers.py` | Added advisory-lock based overlap serialization |
| `services/trip-service/src/trip_service/dependencies.py` | Switched dependency probes/calls to shared HTTP clients |
| `services/trip-service/src/trip_service/workers/enrichment_worker.py` | Reused shared worker client and tolerated unmigrated schema |
| `services/trip-service/src/trip_service/workers/outbox_relay.py` | Refactored outbox flow to batch-claim plus per-event commits |
| `services/trip-service/src/trip_service/observability.py` | Added schema-not-ready handling for cleanup loop |
| `services/trip-service/src/trip_service/main.py` | Closed shared HTTP clients on shutdown |
| `services/trip-service/src/trip_service/routers/trips.py` | Hid soft-deleted trips by default, enforced `If-Match`, persisted manual hashes, and reset retry counters |
| `services/trip-service/tests/test_workers.py` | Added outbox persistence/isolation regression coverage |
| `services/trip-service/tests/test_integration.py` | Added Trip API regression coverage for list/cancel/hash/retry/concurrency |
| `services/trip-service/tests/test_migrations.py` | Verified `trip_outbox.last_error_code` exists after migrations |
| `services/location-service/.env.example` | Added provider probe settings |
| `services/location-service/src/location_service/config.py` | Added provider probe settings and validation |
| `services/location-service/src/location_service/errors.py` | Added `LOCATION_INVALID_FILTER_COMBINATION` helper |
| `services/location-service/src/location_service/models.py` | Replaced active-only pair uniqueness index with live-pair uniqueness index |
| `services/location-service/src/location_service/providers/mapbox_directions.py` | Requested Mapbox directions with `steps=true` |
| `services/location-service/src/location_service/processing/pipeline.py` | Persisted validation deltas and derived segment metadata from intersections |
| `services/location-service/src/location_service/routers/health.py` | Added cached provider live checks and readiness gating |
| `services/location-service/src/location_service/routers/pairs.py` | Enforced new list semantics and mapped live uniqueness integrity errors to 409 |
| `services/location-service/tests/conftest.py` | Stubbed readiness provider probes and reset probe cache between tests |
| `services/location-service/tests/test_pairs_api.py` | Added pair filter and DB uniqueness fallback regression tests |
| `services/location-service/tests/test_processing_flow.py` | Verified validation deltas and segment metadata persistence |
| `services/location-service/tests/test_mock_pipeline.py` | Updated mock provider payloads for step/intersection-aware pipeline execution |
| `services/location-service/tests/test_providers.py` | Verified Mapbox request includes `steps=true` |
| `services/location-service/tests/test_schema_integration.py` | Added readiness and provider probe cache regression coverage |
| `services/location-service/tests/test_unit.py` | Added Turkish dotted-I and NFKC normalization edge-case tests |

## Deleted
| File | Why |
|------|-----|

---

## Notes
- No files were deleted for TASK-0033.
