# BRIEF.md

## Task ID
TASK-0010

## Task Name
Trip Service Prod Hardening and Contract Closure

## Phase
Phase 1-6 cross-cutting stabilization

## Primary Purpose
Trip Service must become production-safe on its locked contracts: strict input validation, transactional writes, hard dependency readiness, Kafka outbox delivery, and the missing Location Service internal route resolution contract.

## Expected Outcome
- `trip-service` manual create, slip ingest, edit, approve, empty-return, cancel, hard-delete, retry-enrichment, list/detail, driver statement, and readiness endpoints enforce the locked contracts and return problem+json on validation/contract failures.
- Removed Excel import/export paths return explicit `404` responses from exact tombstone routes.
- Admin POST idempotency replays the original status/body/headers including `ETag`.
- Trip write paths map named uniqueness races to stable `409` problem codes and enforce one empty-return child per base trip at the database layer.
- Enrichment and outbox workers honor retry ceilings/backoff rules and expose process-safe heartbeats for readiness.
- Kafka is the real broker option, wired by configuration, with non-prod fallbacks.
- `location-service` exposes `POST /internal/v1/routes/resolve` matching the trip enrichment contract.
- Trip-service tests run against Alembic migrations instead of `create_all()`.

## In Scope
- Trip-service contract hardening, persistence fixes, broker wiring, readiness probes, fleet validation client contract, worker heartbeat/retry behavior, Docker packaging, and automated test updates.
- Location-service internal route resolve endpoint and its tests.
- Project memory/task records required by repo workflow.

## Out of Scope
- Fleet-service server implementation outside this repository.
- New Excel import/export service implementation.
- Preserving historical migration compatibility before the clean trip-service baseline.

## Dependencies
- Docker / testcontainers for PostgreSQL-backed tests.
- Kafka client library support in trip-service runtime.
- Existing clean trip-service baseline migration as the starting point for further schema refinement.

## Notes for the Agent
- User locked these decisions already: reset baseline, full IANA timezone, exact 404 tombstones, Kafka transport, all readiness dependencies hard, driver statement `COMPLETED` only, closed enums, full-response idempotency replay, repo-owned image, location resolve fix in scope, fleet refs validate-on-write via bulk endpoint contract.
- Do not touch files outside PLAN.md. Update PLAN.md first if scope expands.
