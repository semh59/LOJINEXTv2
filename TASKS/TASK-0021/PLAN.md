# PLAN.md

## Objective
Lock the Location Service public product contract so a future admin/Tauri frontend can manage points, pairs, lifecycle actions, processing polling, and route-version inspection without calling internal endpoints or reconstructing missing display fields client-side.

## How I Understood the Problem
TASK-0019 made Location Service safe for production use, but its public API was still backend-shaped. Pair responses lacked point display fields and route pointers, processing polling still centered the deprecated pair-prefixed run path, list contracts still used `limit`, operational actions were not role-distinguished for frontend usage, and there were no public route-version detail or geometry endpoints.

## Approach
1. Bootstrap TASK-0021 records and update project memory so this frontend-contract work is tracked separately from TASK-0020 cleanup.
2. Add a dedicated query-contract helper module so pagination and validated sort handling are centralized and testable.
3. Expand Location schemas to lock public `ProfileCode`, enrich pair responses, expand processing-run responses, and add route-version/geometry and bulk-refresh response models.
4. Update points, pairs, processing, and bulk-refresh routers to use the new public contract while keeping compatibility aliases where required.
5. Add a new public routes router for route-version detail and geometry reads.
6. Add dedicated frontend contract tests and route-version API tests, run lint and pytest, and record exact evidence.

## Files That Changed
| File | Action | Why |
|------|--------|-----|
| `MEMORY/DECISIONS.md` | modify | Record the frontend-contract split and public profile-code decision |
| `MEMORY/PROJECT_STATE.md` | modify | Register TASK-0021 and increment the next task ID |
| `TASKS/TASK-0021/BRIEF.md` | create | Task definition |
| `TASKS/TASK-0021/PLAN.md` | create | Locked execution plan |
| `TASKS/TASK-0021/STATE.md` | create | Progress and completion record |
| `TASKS/TASK-0021/CHANGED_FILES.md` | create | File ledger |
| `TASKS/TASK-0021/TEST_EVIDENCE.md` | create | Verification evidence |
| `TASKS/TASK-0021/NEXT_AGENT.md` | create | Handoff summary |
| `TASKS/TASK-0021/DONE_CHECKLIST.md` | create | Completion checklist |
| `services/location-service/src/location_service/main.py` | modify | Wire the new public routers into the app |
| `services/location-service/src/location_service/auth.py` | modify | Add SUPER_ADMIN-only dependency |
| `services/location-service/src/location_service/schemas.py` | modify | Lock public frontend schemas |
| `services/location-service/src/location_service/query_contracts.py` | create | Centralize pagination/sort contract logic |
| `services/location-service/src/location_service/routers/points.py` | modify | Add `per_page`, deprecated `limit`, validated `sort`, and stable meta |
| `services/location-service/src/location_service/routers/pairs.py` | modify | Enrich pair responses and add public list search/filter/sort contract |
| `services/location-service/src/location_service/routers/approval.py` | modify | Return enriched `PairResponse` payloads |
| `services/location-service/src/location_service/routers/processing.py` | modify | Add canonical processing-run endpoints, list history, and SUPER_ADMIN force-fail |
| `services/location-service/src/location_service/routers/bulk_refresh.py` | modify | Make bulk refresh SUPER_ADMIN-only and schema-backed |
| `services/location-service/src/location_service/routers/routes_public.py` | create | Public route-version detail and geometry endpoints |
| `services/location-service/tests/test_auth.py` | modify | Cover SUPER_ADMIN-only operations |
| `services/location-service/tests/test_audit_findings.py` | modify | Keep audit regression coverage aligned with auth changes |
| `services/location-service/tests/test_points_api.py` | modify | Cover pagination/sort/frontend list contract |
| `services/location-service/tests/test_pairs_api.py` | modify | Cover enriched pair payloads and frontend list contract |
| `services/location-service/tests/test_contract.py` | create | Dedicated public frontend contract coverage |
| `services/location-service/tests/test_route_versions_api.py` | create | Route-version detail and geometry coverage |

## Risks
- The public contract is broader than the old backend-shaped API, so tests must assert compatibility aliases and new canonical paths precisely.
- Pair enrichment relies on joined point reads rather than denormalized DB columns; query bugs would surface as missing frontend fields.
- Existing unrelated dirty files in the repo, especially under `trip-service`, must remain untouched.

## Test Cases
1. Public `/v1/*` endpoints still require bearer auth.
2. `force-fail` and bulk refresh reject `ADMIN` and allow `SUPER_ADMIN`.
3. Points list accepts `per_page`, still accepts deprecated `limit`, prefers `per_page`, and validates `sort`.
4. Pairs list/detail responses include profile, point display fields, route pointers, and pending-draft state.
5. Pairs list supports `profile_code`, point-based search, and validated sort values.
6. Canonical `GET /v1/processing-runs/{run_id}` matches the deprecated alias payload.
7. `GET /v1/pairs/{pair_id}/processing-runs` returns paginated run history.
8. `GET /v1/routes/{route_id}/versions/{version_no}` returns route-version detail.
9. `GET /v1/routes/{route_id}/versions/{version_no}/geometry` returns ordered 2D coordinates.
10. `uv run --directory services/location-service --extra dev ruff check src tests` passes.
11. `uv run --directory services/location-service --extra dev pytest` passes.

## Out of Scope
- TASK-0020 cleanup, worker redesign, or schema pruning.
- Trip Service or frontend code changes.
- Any Alembic migration.

## Completion Criterion
- The frontend-facing Location contract is explicit, tested, and queryable without internal endpoints.
- Pair and processing payloads expose the fields a UI needs to render list/detail/workflow screens.
- Route-version metrics and geometry are available through public endpoints.
- The work is documented as a standalone task separate from cleanup.
