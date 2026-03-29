# BRIEF.md

## Objective
Make `services/location-service` frontend-ready by locking a clean public product contract for points, pairs, processing runs, and route-version inspection without changing Trip-facing internal endpoints.

## In Scope
- Location Service public `/v1/*` contract only.
- Public request/response schema expansion for frontend use.
- Canonical `per_page` + validated `sort` list contracts.
- Public route-version detail and geometry read endpoints.
- SUPER_ADMIN-only contract for public operational actions.
- Dedicated frontend-contract tests and task/memory records.

## Out of Scope
- Any frontend/Tauri code.
- `trip-service` changes.
- Location internal `/internal/v1/*` contract changes.
- TASK-0020 cleanup and worker redesign.
- Alembic migrations or DB schema changes.

## Success Criteria
- Pair and point list/detail responses are frontend-complete without client-side enrichment calls.
- Public processing-run polling has canonical list/detail endpoints.
- Public route-version detail and geometry endpoints exist and are tested.
- Public contract behavior is covered by dedicated Location contract tests.
- `trip-service` remains untouched.
