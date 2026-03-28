# Audit Report — Trip + Location Services (TASK-0012)

Status: Complete

Scope: line-by-line review of 77 files (12,075 total lines) across:
- `services/trip-service/src/trip_service/**`
- `services/trip-service/tests/**`
- `services/location-service/src/location_service/**`
- `services/location-service/tests/**`

Review method: source + tests read end-to-end, with test execution evidence captured in `TASKS/TASK-0012/TEST_EVIDENCE.md`.

## Critical
None found.

## High
1. Location-service pair code generation raises at runtime
   - File: `services/location-service/src/location_service/domain/codes.py:10`
   - Impact: `generate_pair_code()` uses `ulid.ULID()` without a buffer and raises `TypeError`, which breaks:
     - `POST /v1/pairs`
     - CSV import pairing
     - any processing flow that relies on pair code generation
   - Evidence: location-service pytest failures in `test_pairs_api.py`, `test_processing_flow.py`, and `test_unit.py`
   - Mitigation: switch to `ulid.new()` (python-ulid) or equivalent ULID generator that returns a string.

## Medium
1. Location-service test contract drift on If-Match for point updates
   - File: `services/location-service/tests/test_points_api.py:44`
   - Impact: test expects `PATCH /v1/points/{id}` to succeed without `If-Match`, but API returns `428` (precondition required). Either the API is stricter than tests or tests are stale.
   - Mitigation: align tests/docs with the intended contract or relax If-Match enforcement.

2. Location-service schema integration tests are non-isolated
   - File: `services/location-service/tests/test_schema_integration.py:31`
   - Impact: fixed point codes (e.g., `TR_IST_01`) collide across tests, causing nondeterministic failures.
   - Mitigation: use unique codes per test or purge tables between tests.

## Low
1. Location-service repo-wide lint failures (import ordering, unused imports)
   - Files:
     - `services/location-service/src/location_service/routers/export_router.py:3`
     - `services/location-service/tests/test_audit_findings.py:7`
     - `services/location-service/tests/test_processing_flow.py:3`
   - Impact: `ruff check src tests` fails for location-service.
   - Mitigation: run `ruff check --fix` and remove unused imports.

2. AsyncMock warnings in location-service pipeline tests
   - File: `services/location-service/tests/test_mock_pipeline.py`
   - Impact: warnings indicate AsyncMock calls not awaited; test reliability risk.
   - Mitigation: await mocked coroutines or adjust mocks to sync where appropriate.

## Info
1. Trip-service error message uses legacy field name
   - File: `services/trip-service/src/trip_service/timezones.py:24`
   - Impact: validation error mentions `trip_datetime_local`, but the API field is `trip_start_local`.
   - Mitigation: update error string for clarity.
