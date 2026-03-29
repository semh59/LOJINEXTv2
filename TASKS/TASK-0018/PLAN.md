# PLAN.md

## Objective
Location Service will lose its import/export surface and enforce the intended point/pair/processing/resolve contracts with stable problem+json behavior.

## How I Understand the Problem
Location Service currently passes its tests but still contains dead import/export ownership, latent runtime failures, and request/response ambiguities. Trip Service already models Excel as a separate service, so this task must narrow Location Service to route authority concerns only and fix the exposed contract drifts without touching Trip Service.

## Approach
1. Open TASK-0018 records and update project memory with the new cleanup decision and active task.
2. Remove import/export routers, processing helpers, schema models, env vars, dependencies, metrics, and DB structures from Location Service.
3. Add a request-validation problem+json handler and tighten point create/update error mapping.
4. Fix pair list/patch behavior, concurrency semantics, and pair row-version updates across state mutations.
5. Fix processing guards and internal route resolution semantics.
6. Update tests to cover the new contract and remove import/export coverage.
7. Run lint, pytest, and Alembic migration verification; record evidence and handoff.

## Files That Will Change
Nothing outside this list gets touched.

| File | Action | Why |
|------|--------|-----|
| `MEMORY/DECISIONS.md` | modify | Record the architectural ownership change |
| `MEMORY/PROJECT_STATE.md` | modify | Register TASK-0018 and advance next task ID |
| `TASKS/TASK-0018/BRIEF.md` | modify | Task definition |
| `TASKS/TASK-0018/PLAN.md` | modify | Execution plan |
| `TASKS/TASK-0018/STATE.md` | modify | Progress tracking |
| `TASKS/TASK-0018/CHANGED_FILES.md` | modify | Final file ledger |
| `TASKS/TASK-0018/TEST_EVIDENCE.md` | modify | Final test evidence |
| `TASKS/TASK-0018/NEXT_AGENT.md` | modify | Final handoff |
| `TASKS/TASK-0018/DONE_CHECKLIST.md` | modify | Final completion record |
| `services/location-service/src/location_service/main.py` | modify | Remove import/export router and register validation handler |
| `services/location-service/src/location_service/config.py` | modify | Remove import/export/storage settings |
| `services/location-service/src/location_service/errors.py` | modify | Add generic validation handler and remove import/export errors |
| `services/location-service/src/location_service/observability.py` | modify | Remove import/export metrics |
| `services/location-service/src/location_service/enums.py` | modify | Remove import/export-specific enums |
| `services/location-service/src/location_service/models.py` | modify | Remove import/export schema objects and `import_job_id` |
| `services/location-service/src/location_service/schemas.py` | modify | Remove ambiguous request fields and fix docs |
| `services/location-service/src/location_service/middleware.py` | modify | Add route-pair If-Match support |
| `services/location-service/src/location_service/routers/points.py` | modify | Fix point validation and DB error mapping |
| `services/location-service/src/location_service/routers/pairs.py` | modify | Fix pair create/list/patch/delete semantics |
| `services/location-service/src/location_service/routers/processing.py` | modify | Fix calculate/refresh state guards |
| `services/location-service/src/location_service/routers/internal_routes.py` | modify | Enforce ACTIVE version resolution and ambiguity handling |
| `services/location-service/src/location_service/routers/approval.py` | modify | Bump pair row_version on approval/discard mutations |
| `services/location-service/src/location_service/processing/approval.py` | modify | Bump pair row_version on approve flow |
| `services/location-service/src/location_service/processing/pipeline.py` | modify | Bump pair row_version when draft pointers change |
| `services/location-service/src/location_service/routers/import_router.py` | delete | Remove import endpoint |
| `services/location-service/src/location_service/routers/export_router.py` | delete | Remove export endpoint |
| `services/location-service/src/location_service/routers/import_export.py` | delete | Remove aggregator router |
| `services/location-service/src/location_service/processing/import_logic.py` | delete | Remove import processing |
| `services/location-service/src/location_service/processing/export_logic.py` | delete | Remove export processing |
| `services/location-service/alembic/versions/0d5f12e97db6_remove_import_export.py` | create | Forward migration for schema cleanup |
| `services/location-service/pyproject.toml` | modify | Remove unused runtime dependencies |
| `services/location-service/uv.lock` | modify | Sync dependency lockfile |
| `services/location-service/.env.example` | modify | Remove dead env surface |
| `services/location-service/tests/conftest.py` | modify | Register validation handler and keep test app aligned |
| `services/location-service/tests/test_points_api.py` | modify | Cover tightened point contract |
| `services/location-service/tests/test_pairs_api.py` | modify | Cover pair filter/patch/guard behavior |
| `services/location-service/tests/test_internal_routes.py` | modify | Cover ACTIVE version checks and ambiguity |
| `services/location-service/tests/test_processing_flow.py` | modify | Remove import/export coverage |
| `services/location-service/tests/test_audit_findings.py` | modify | Replace old import/export findings with current contract checks |

## Risks
- The new validation handler must preserve existing stable error codes where required and not hide actionable details.
- Removing import/export schema requires a correct forward migration path; test metadata creation alone is not sufficient proof.
- Pair `row_version` changes touch multiple mutation paths and could leave inconsistent ETag behavior if one path is missed.

## Test Cases
1. Test that invalid point payloads return `422 application/problem+json` with `LOCATION_REQUEST_VALIDATION_ERROR`.
2. Test that blank point names return `422 LOCATION_POINT_NAME_BLANK`.
3. Test that duplicate coordinates and invalid coordinates map to stable point error codes instead of 500.
4. Test that immutable point field updates return `422 LOCATION_POINT_IMMUTABLE_FIELD_MODIFICATION`.
5. Test that point name conflicts on update return `409 LOCATION_POINT_NAME_CONFLICT`.
6. Test that creating a pair over a soft-deleted pair returns `409 LOCATION_ROUTE_PAIR_ALREADY_EXISTS_DELETED`.
7. Test that `GET /v1/pairs?is_active=` applies the intended filter semantics.
8. Test that pair patch requires `If-Match`, rejects `is_active`, and increments `row_version`.
9. Test that calculate on ACTIVE and refresh on non-ACTIVE return the intended conflict codes.
10. Test that internal resolve ignores non-ACTIVE route versions and returns `ROUTE_AMBIGUOUS` on multiple active candidates.
11. Test that `/v1/import`, `/v1/export`, and OpenAPI no longer expose import/export.
12. Test that Alembic upgrades successfully through the new cleanup migration.

## Out of Scope
- Trip Service implementation or tests.
- New external Excel/import-export service work.
- Rewriting the initial Location Service migration.

## Completion Criterion
- Import/export code, schema, config, metrics, and dependencies are gone from Location Service.
- The identified point/pair/processing/resolve drifts are fixed and covered by tests.
- `ruff`, `pytest`, and Alembic upgrade succeed with evidence recorded.
- TASK-0018 records and project memory reflect the new state.

## Plan Revisions
None yet.
