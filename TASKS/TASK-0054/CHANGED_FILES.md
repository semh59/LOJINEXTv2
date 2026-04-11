# TASK-0054 — Changed Files

## Runtime Code

1. `services/trip-service/src/trip_service/middleware.py`
   - Unified ETag output to canonical quoted version format: `"{version}"`
   - Updated If-Match parsing to support canonical numeric format first
   - Kept backward compatibility for legacy `"trip-{id}-v{version}"` format
   - Simplified `require_trip_if_match` to version-only optimistic lock check

2. `services/trip-service/src/trip_service/service.py`
   - Added strict `If-Match` requirement (428) for:
     - `edit_trip`
     - `approve_trip`
     - `reject_trip`
     - `cancel_trip`
   - Preserved 412 behavior for stale/invalid version values

## Database Migration

3. `services/trip-service/alembic/versions/a9c8e7f6d5b4_trip_outbox_payload_json_text.py`
   - Added migration to align `trip_outbox.payload_json` with platform standard:
     - `upgrade`: `JSONB -> Text`
     - `downgrade`: `Text -> JSONB`

## Task Tracking

4. `TASKS/TASK-0054/STATE.md`
   - Updated progress and blocker notes for production-hardening work

## Follow-up Runtime Hardening (2026-04-11, audit-driven)

5. `services/trip-service/src/trip_service/workers/outbox_relay.py`
   - Fixed double JSON serialization in relay publish payload (`payload=row.payload_json`).

6. `services/trip-service/src/trip_service/resiliency.py`
   - Added `CircuitBreaker.state` property used by readiness probes.

7. `services/trip-service/src/trip_service/middleware.py`
   - Added `HTTP_REQUESTS_TOTAL.inc()` in Prometheus middleware.
   - Normalized `status_code` label as string.

8. `services/trip-service/src/trip_service/saga.py`
   - Replaced `settings.broker_type` with `settings.resolved_broker_type` to avoid `None` broker crash.

9. `services/trip-service/src/trip_service/http_clients.py`
   - Added lock fast-path return to reduce unnecessary async lock contention.

10. `services/trip-service/src/trip_service/dependencies.py`
    - Removed request-time retry wrappers from fleet/location HTTP calls (fail-fast alignment).

11. `packages/platform-common/src/platform_common/data_quality.py` (new)
    - Introduced shared `compute_data_quality_flag(...)` implementation.

12. `packages/platform-common/src/platform_common/__init__.py`
    - Exported `compute_data_quality_flag` from package root.

13. `services/trip-service/src/trip_service/trip_helpers.py`
    - Delegated local quality-flag helper to `platform_common.compute_data_quality_flag`.

14. `services/trip-service/src/trip_service/auth.py`
    - Moved JWKS probe off event loop (`anyio.to_thread.run_sync`).
    - Made `auth_verify_status()` async.

15. `services/trip-service/src/trip_service/routers/health.py`
    - Updated readiness auth probe call to await async `auth_verify_status()`.

16. `services/trip-service/src/trip_service/routers/driver_statement.py`
    - Replaced `del auth` anti-pattern with `_ = auth`.

17. `services/trip-service/src/trip_service/routers/trips.py`
    - Replaced all `del auth` usages with `_ = auth`.

18. `services/trip-service/src/trip_service/workers/enrichment_worker.py`
    - Removed duplicate local data-quality function and local route-resolve helper.
    - Refactored processing into load/resolve/save phases to avoid HTTP while DB session is open.
    - Applied route pair context through `fetch_trip_context(...) + apply_trip_context(...)` on READY path.

19. `TASKS/TASK-0054/CHANGED_FILES.md`
    - Appended this follow-up hardening summary.
