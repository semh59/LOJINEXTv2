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
