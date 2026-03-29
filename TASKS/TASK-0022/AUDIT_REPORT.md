# Audit Report — Location Service (TASK-0022)

Status: Complete

Scope: line-by-line review of location-service source and tests (see TASKS/TASK-0022/PLAN.md inventory).

## Critical

## High
1. Pair code generation raises at runtime
   - File: services/location-service/src/location_service/domain/codes.py
   - Impact: generate_pair_code() returns f"RP_{ULID()}" using python-ulid ULID() constructor without a buffer, which raises TypeError in production. This breaks POST /v1/pairs and all flows that create route pairs.
   - Evidence: code inspection; prior pytest failures in test_pairs_api when ULID() raises.
   - Mitigation: replace ULID() with ulid.new() or ULID.from_bytes/ULID.from_str (per python-ulid API) and return str.

## Medium
1. Load/soak run fails on internal route resolve after calculate + approve
   - Files: TASKS/TASK-0022/scripts/location_load.py (execution), services/location-service/src/location_service/routers/internal_routes.py, services/location-service/src/location_service/processing/approval.py
   - Impact: During load/soak, POST /internal/v1/routes/resolve returned 404 LOCATION_ROUTE_RESOLUTION_NOT_FOUND even after calculate and approve steps, causing the prod-hard load test to fail early. This indicates a potential race or mismatch between approval and internal resolve expectations for active pairs.
   - Evidence: Load test output in TASKS/TASK-0022/TEST_EVIDENCE.md (404 from internal resolve).
   - Mitigation: Investigate whether approve flow fully activates route versions before internal resolve, or adjust load scenario to ensure active forward/reverse pointers are set before calling resolve.

## Low
1. Pytest requires PYTHONPATH to import location_service
   - Files: services/location-service/tests/conftest.py, packaging config
   - Impact: `pytest` from repo root fails with ModuleNotFoundError unless PYTHONPATH=src is set; this is a test ergonomics issue rather than a product bug.
   - Evidence: Initial pytest run failed without PYTHONPATH.
   - Mitigation: Document required invocation or add pytest.ini/pythonpath configuration.

## Info
- Ruff lint passes cleanly for location-service source and tests.
- Full pytest passes when PYTHONPATH=src is set.
