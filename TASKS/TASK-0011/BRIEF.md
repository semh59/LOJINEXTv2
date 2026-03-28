# BRIEF.md

## Task ID
TASK-0011

## Task Name
Trip Service Product Contract Alignment for Tauri Desktop

## Phase
Phase 2-6 cross-cutting contract realignment

## Primary Purpose
Trip service and its location-service dependency must enforce the locked product contract for manual trips, imported trips, overlap blocking, source-aware review, and super-admin deletion so a future Tauri desktop client can rely on a production-safe backend contract.

## Expected Outcome
- Public trip mutation endpoints require bearer-token auth and distinguish `ADMIN` vs `SUPER_ADMIN`.
- Manual trip creation uses `route_pair_id`, persists origin/destination snapshots and planned duration, requires `vehicle_id`, and enforces the admin/super-admin time rules.
- Empty-return creation derives reverse trip context from the base trip and uses the `-B` suffix.
- Telegram full ingest, Telegram fallback ingest, Excel ingest, and Excel export feed exist as internal structured APIs with stable idempotency and review-state behavior.
- Trip overlap checks block conflicting driver/vehicle/trailer windows with stable `409` codes.
- Hard delete becomes a reasoned super-admin action with immutable audit persistence.
- Driver statement enforces `COMPLETED` only and a maximum `31` day range.
- Location service exposes the trip-context endpoint required for duration-based trip creation and overlap checks.

## In Scope
- Trip-service auth, schemas, models, migrations, routers, dependency clients, worker-safe rules, and tests needed to match the locked product contract.
- Location-service internal trip-context endpoint and its tests.
- New task/memory records required by the repository workflow.

## Out of Scope
- Building the Tauri desktop app itself.
- Telegram-service implementation details such as OCR, Telegram user resolution, or PDF rendering.
- Excel-service file parsing and file rendering outside the structured internal contract owned by trip-service.
- Fleet-service server implementation outside this repository.

## Dependencies
- Existing TASK-0010 baseline trip-service cleanup and hardening changes remain the base state.
- Docker/testcontainers remain available for PostgreSQL-backed test execution.
- Fleet-service and Telegram/Excel producers are represented here by contracts and stubs, not full external implementations.

## Notes for the Agent
- The user locked Tauri frontend, bearer-token auth, separate empty-return action, Excel export including empty returns, and Telegram PDF ownership outside trip-service.
- Trip numbers remain globally unique.
- The current repo has no real Tauri scaffold; this task only makes the backend contract ready for that future app.
