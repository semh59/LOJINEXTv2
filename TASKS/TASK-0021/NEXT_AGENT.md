# NEXT_AGENT.md

## What Landed
- Location Service now has a frontend-oriented public contract for points, pairs, processing runs, and route-version inspection.
- Canonical public processing-run endpoints are:
  - `GET /v1/processing-runs/{run_id}`
  - `GET /v1/pairs/{pair_id}/processing-runs`
- The deprecated compatibility alias `GET /v1/pairs/processing-runs/{run_id}` still exists and returns the same payload.
- New public route inspection endpoints are:
  - `GET /v1/routes/{route_id}/versions/{version_no}`
  - `GET /v1/routes/{route_id}/versions/{version_no}/geometry`
- Public operational actions now require `SUPER_ADMIN`:
  - `POST /v1/processing-runs/{run_id}/force-fail`
  - `POST /v1/bulk-refresh/jobs`

## Files to Read First
1. `TASKS/TASK-0021/PLAN.md`
2. `TASKS/TASK-0021/STATE.md`
3. `TASKS/TASK-0021/TEST_EVIDENCE.md`
4. `services/location-service/src/location_service/query_contracts.py`
5. `services/location-service/src/location_service/routers/pairs.py`
6. `services/location-service/src/location_service/routers/processing.py`
7. `services/location-service/src/location_service/routers/routes_public.py`
8. `services/location-service/tests/test_contract.py`

## Temporary / Compatibility Decisions Still Present
- `limit` is still accepted as a deprecated alias for `per_page`.
- `GET /v1/pairs/processing-runs/{run_id}` is still kept as a deprecated compatibility alias.
- Pair enrichment is done through joined reads; there are no denormalized display columns.

## If You Continue This Work
- The next logical follow-up is TASK-0020 cleanup, not more frontend-contract expansion.
- If you remove compatibility aliases later, update both `query_contracts.py` callers and contract tests together.
- If you add more frontend screens, prefer extending the existing public route/version surfaces rather than exposing internal endpoints.

## Things Explicitly Not Touched
- `trip-service`
- Location internal `/internal/v1/*` endpoints
- DB schema / Alembic
