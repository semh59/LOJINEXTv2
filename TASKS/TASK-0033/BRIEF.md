# BRIEF.md

## Task ID
TASK-0033

## Task Name
Trip/Location Audit Remediation

## Phase
Phase 7 - Production Ready

## Primary Purpose
Close the remaining current-HEAD Trip and Location audit gaps without reopening already-resolved scope.

## Expected Outcome
- `GET /api/v1/trips` hides `SOFT_DELETED` rows unless `status=SOFT_DELETED` is requested.
- `POST /api/v1/trips/{trip_id}/cancel` enforces `If-Match` even for already soft-deleted trips.
- Trip outbox rows persist `last_error_code`, publish with per-event commits, and keep stale-claim recovery.
- Trip overlap checks serialize concurrent writers with advisory transaction locks.
- `GET /v1/pairs` hides `SOFT_DELETED` rows by default, treats `is_active=false` as `DRAFT`, and rejects contradictory filters.
- Location route versions persist validation deltas and segment metadata derived from Mapbox intersections.
- Location `/ready` uses cached live provider probes and returns 503 on real provider unavailability.

## In Scope
- TASK-0033 scaffolding and memory updates.
- Trip Service outbox/model/list/cancel/retry/hash/concurrency fixes.
- Shared Trip HTTP clients and schema-not-ready worker handling.
- Location pair uniqueness/index/filter/error handling.
- Location route validation delta persistence, segment metadata enrichment, cached provider readiness, and normalization edge-case tests.
- Regression tests and targeted pytest runs for both services.

## Out of Scope
- Reopened work for stale audit findings already fixed in current HEAD.
- TASK-0020 persistent worker redesign beyond the readiness/probe hardening explicitly listed here.
- Trip public API changes beyond the locked behaviors above.
- Rewriting historical Trip migrations.

## Dependencies
- Existing Trip and Location services from TASK-0019 through TASK-0032.
- PostgreSQL-backed pytest/testcontainers setup for both services.
- Existing Mapbox/ORS provider abstractions and health surfaces.

## Notes for the Agent
- Keep TASK-0033 separate from `TASKS/TASK-0020`.
- Hide tombstones by default.
- Use per-event outbox commits, cached provider probes, and hybrid concurrency control (DB uniqueness for pairs + advisory locks for trips).
- Do not edit old Trip Alembic revisions for `last_error_code`; fix model parity in ORM and cover with tests.
