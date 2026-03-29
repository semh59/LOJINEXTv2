# PLAN.md

## Objective
Produce a location-service-only deep audit plus prod-hard test evidence focused on API/endpoint behavior, database/migrations, and public/internal contract alignment.

## How I Understand the Problem
The request is to re-audit location-service line by line with emphasis on contract surfaces and database correctness, then execute a full, production-grade test matrix (lint, pytest, migrations, live-provider smoke, and load/soak). No code or contract changes should be made; only findings and evidence should be recorded.

## Approach
1. Inventory location-service source and test files and freeze scope.
2. Read router files, schemas, auth, query contracts, and errors line by line; trace each endpoint to its contracts and compare with tests.
3. Read models, database layer, and alembic migrations line by line; validate constraints, indexes, nullable semantics, enums, and reversibility.
4. Record findings with severity, impact, evidence, and mitigation guidance.
5. Run prod-hard test matrix for location-service only (lint, pytest, alembic upgrade, docker smoke with live providers, load/soak).
6. Capture test outputs and update task records for handoff.

## Files That Will Change
Nothing outside this list gets touched.
New file needed during build -> update this list first.

| File | Action | Why |
|------|--------|-----|
| MEMORY/PROJECT_STATE.md | modify | Register TASK-0022 and advance Next Task ID. |
| TASKS/TASK-0022/BRIEF.md | modify | Set task definition. |
| TASKS/TASK-0022/PLAN.md | modify | Record detailed plan and audit scope. |
| TASKS/TASK-0022/STATE.md | modify | Track progress and risks. |
| TASKS/TASK-0022/AUDIT_REPORT.md | create | Record audit findings. |
| TASKS/TASK-0022/TEST_EVIDENCE.md | modify | Record command outputs. |
| TASKS/TASK-0022/CHANGED_FILES.md | modify | Track file changes. |
| TASKS/TASK-0022/NEXT_AGENT.md | modify | Handoff notes. |
| TASKS/TASK-0022/DONE_CHECKLIST.md | modify | Completion checklist. |
| TASKS/TASK-0022/scripts/location_load.py | create | Load/soak script for location-service. |

## Audit Scope (Inventory)
Source files:
- services/location-service/src/location_service/__init__.py
- services/location-service/src/location_service/auth.py
- services/location-service/src/location_service/config.py
- services/location-service/src/location_service/database.py
- services/location-service/src/location_service/enums.py
- services/location-service/src/location_service/errors.py
- services/location-service/src/location_service/main.py
- services/location-service/src/location_service/middleware.py
- services/location-service/src/location_service/models.py
- services/location-service/src/location_service/observability.py
- services/location-service/src/location_service/query_contracts.py
- services/location-service/src/location_service/schemas.py
- services/location-service/src/location_service/domain/classification.py
- services/location-service/src/location_service/domain/codes.py
- services/location-service/src/location_service/domain/distributions.py
- services/location-service/src/location_service/domain/hashing.py
- services/location-service/src/location_service/domain/normalization.py
- services/location-service/src/location_service/providers/mapbox_directions.py
- services/location-service/src/location_service/providers/mapbox_terrain.py
- services/location-service/src/location_service/providers/ors_validation.py
- services/location-service/src/location_service/processing/approval.py
- services/location-service/src/location_service/processing/bulk.py
- services/location-service/src/location_service/processing/pipeline.py
- services/location-service/src/location_service/routers/__init__.py
- services/location-service/src/location_service/routers/approval.py
- services/location-service/src/location_service/routers/bulk_refresh.py
- services/location-service/src/location_service/routers/health.py
- services/location-service/src/location_service/routers/internal_routes.py
- services/location-service/src/location_service/routers/pairs.py
- services/location-service/src/location_service/routers/points.py
- services/location-service/src/location_service/routers/processing.py
- services/location-service/src/location_service/routers/removed_endpoints.py
- services/location-service/src/location_service/routers/routes_public.py

Test files:
- services/location-service/tests/conftest.py
- services/location-service/tests/test_audit_findings.py
- services/location-service/tests/test_auth.py
- services/location-service/tests/test_config.py
- services/location-service/tests/test_contract.py
- services/location-service/tests/test_internal_routes.py
- services/location-service/tests/test_mock_pipeline.py
- services/location-service/tests/test_pairs_api.py
- services/location-service/tests/test_points_api.py
- services/location-service/tests/test_processing_flow.py
- services/location-service/tests/test_providers.py
- services/location-service/tests/test_route_versions_api.py
- services/location-service/tests/test_schema.py
- services/location-service/tests/test_schema_integration.py
- services/location-service/tests/test_unit.py

## Risks
- Live provider smoke may fail if API keys are missing, expired, or rate-limited.
- Load/soak test can cause throttling or resource pressure on local services.
- Existing lint/pytest failures may block a clean test run; record exact output.

## Test Cases
1. Run `ruff check src tests` in services/location-service.
2. Run full `pytest` in services/location-service.
3. Run `alembic upgrade head` on a clean DB using location-service config.
4. Run docker smoke with live providers: `TASKS/TASK-0012/scripts/smoke.ps1 -UseLiveProviders`.
5. Run load/soak: `python TASKS/TASK-0022/scripts/location_load.py` with required env vars.

## Out of Scope
- Any code or contract changes.
- Trip-service tests or audits.
- Cleanup/architecture work (TASK-0020).

## Completion Criterion
- AUDIT_REPORT.md contains line-by-line findings with severity, impact, evidence, and mitigation.
- TEST_EVIDENCE.md contains raw outputs for all five test cases (or explicit reasons if any were skipped).
- STATE.md, CHANGED_FILES.md, and NEXT_AGENT.md reflect actual work done.

---

## Plan Revisions

### 2026-03-29 Initial plan recorded
What changed:
- Created full plan and inventory scope for TASK-0022.
Why:
- Required before any task execution per RULE-01.
