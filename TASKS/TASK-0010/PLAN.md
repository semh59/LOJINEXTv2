# PLAN.md

## Objective
Trip-service and its required location-service dependency surface will enforce the locked production contracts with verified persistence, readiness, broker, worker, and test behavior that do not exist today.

## How I Understand the Problem
The repo already removed trip-service Excel/weather responsibilities, but the remaining service is still not production-safe. Timezone parsing is inconsistent, admin idempotency is not atomic, DB races leak as `500`, readiness is mostly fake, Kafka is not wired, worker retry ceilings are incorrect, and trip enrichment depends on a location-service internal endpoint that does not exist. The task is to close those gaps without reopening removed Excel scope, while keeping driver statement inside trip-service and adding the missing location-service internal resolve contract.

## Approach
1. Create the task records and lock the implementation scope in repository memory before changing code.
2. Harden trip-service core contracts: timezone helpers, closed enums, admin actor enforcement, fleet validation client contract, exact tombstone routes, improved problem+json handling, and stable trip/write helpers.
3. Make trip-service persistence and workers production-safe: transactional idempotency replay, named uniqueness constraints with `409` mapping, one-empty-return DB constraint, Kafka broker implementation, heartbeat tracking, readiness probes, and retry/backoff fixes.
4. Add the missing location-service internal route resolve endpoint and tests that prove exact-match route resolution and not-found behavior.
5. Rework trip-service test infrastructure to use Alembic migrations and add coverage for the hardened contracts, worker logic, readiness, broker behavior, and removed endpoint tombstones.
6. Add trip-service container packaging, run lint/tests, record evidence, and update project memory/task handoff files to reflect the new reality.

## Files That Will Change
Nothing outside this list gets touched.
New file needed during build -> update this list first.

| File | Action | Why |
|------|--------|-----|
| `TASKS/TASK-0010/BRIEF.md` | create | Define task scope and purpose |
| `TASKS/TASK-0010/PLAN.md` | create | Lock the implementation plan before code |
| `TASKS/TASK-0010/STATE.md` | create | Track progress and risks during build |
| `TASKS/TASK-0010/CHANGED_FILES.md` | create | Record touched files per repo rules |
| `TASKS/TASK-0010/TEST_EVIDENCE.md` | create | Capture actual verification output |
| `TASKS/TASK-0010/NEXT_AGENT.md` | create | Leave a complete handoff record |
| `MEMORY/PROJECT_STATE.md` | modify | Register the new active task and updated project state |
| `MEMORY/DECISIONS.md` | modify | Record architecture and rollout decisions applied in code |
| `services/trip-service/pyproject.toml` | modify | Add runtime dependencies and packaging requirements |
| `services/trip-service/.env.example` | modify | Document the new broker and readiness-related environment surface |
| `services/trip-service/uv.lock` | modify | Capture resolved dependency changes if `uv` updates the lock file |
| `services/trip-service/Dockerfile` | create | Add repo-owned production container image |
| `services/trip-service/.dockerignore` | create | Keep the image build clean and deterministic |
| `services/trip-service/alembic/versions/a1b2c3d4e5f6_trip_service_baseline.py` | modify | Refine the clean baseline schema for prod constraints |
| `services/trip-service/src/trip_service/config.py` | modify | Add broker, timeout, and readiness configuration |
| `services/trip-service/src/trip_service/broker.py` | modify | Implement Kafka broker and broker health checks |
| `services/trip-service/src/trip_service/database.py` | modify | Support test/migration-safe engine usage if required |
| `services/trip-service/src/trip_service/enums.py` | modify | Add/adjust strict enum types used by contracts |
| `services/trip-service/src/trip_service/errors.py` | modify | Add new stable problem codes and dependency errors |
| `services/trip-service/src/trip_service/middleware.py` | modify | Centralize strict ETag/timezone/date range behavior |
| `services/trip-service/src/trip_service/models.py` | modify | Add schema-level constraints and idempotency headers field |
| `services/trip-service/src/trip_service/observability.py` | modify | Wire metrics and cleanup behavior to the hardened workers |
| `services/trip-service/src/trip_service/main.py` | modify | Wire routers, broker selection, and background workers |
| `services/trip-service/src/trip_service/schemas.py` | modify | Tighten request validation and closed enums |
| `services/trip-service/src/trip_service/trip_helpers.py` | modify | Keep shared trip mapping helpers consistent |
| `services/trip-service/src/trip_service/routers/trips.py` | modify | Apply contract, idempotency, validation, and persistence fixes |
| `services/trip-service/src/trip_service/routers/driver_statement.py` | modify | Enforce statement filtering and shared timezone behavior |
| `services/trip-service/src/trip_service/routers/health.py` | modify | Implement real hard dependency readiness |
| `services/trip-service/src/trip_service/routers/removed_endpoints.py` | create | Return exact 404 tombstones for removed Excel routes |
| `services/trip-service/src/trip_service/dependencies.py` | create | Centralize fleet/location probes and validation clients |
| `services/trip-service/src/trip_service/timezones.py` | create | Provide shared timezone parsing/conversion helpers |
| `services/trip-service/src/trip_service/worker_heartbeats.py` | create | Persist worker heartbeats across processes for readiness |
| `services/trip-service/src/trip_service/workers/enrichment_worker.py` | modify | Fix claim eligibility, retry ceiling, probes, and heartbeat updates |
| `services/trip-service/src/trip_service/workers/outbox_relay.py` | modify | Fix backoff/dead-letter behavior and heartbeat updates |
| `services/trip-service/tests/conftest.py` | modify | Switch tests to Alembic-backed isolated databases and dependency stubs |
| `services/trip-service/tests/test_integration.py` | modify | Cover hardened endpoint flows and tombstones |
| `services/trip-service/tests/test_unit.py` | modify | Cover helper/worker/unit-level contract logic |
| `services/trip-service/tests/test_contract.py` | modify | Cover public problem+json and readiness contracts |
| `services/trip-service/tests/test_migrations.py` | modify | Verify refined baseline schema details |
| `services/trip-service/tests/test_repo_cleanliness.py` | modify | Keep repo cleanliness checks aligned with new contract surface |
| `services/trip-service/tests/test_workers.py` | create | Verify outbox and enrichment retry behavior |
| `services/location-service/src/location_service/main.py` | modify | Register the internal resolve router |
| `services/location-service/src/location_service/schemas.py` | modify | Add request/response schemas for internal route resolve |
| `services/location-service/src/location_service/errors.py` | modify | Add stable not-found/validation errors for route resolve |
| `services/location-service/src/location_service/routers/internal_routes.py` | create | Implement the internal route resolution endpoint |
| `services/location-service/tests/conftest.py` | modify | Expose the new router in tests |
| `services/location-service/tests/test_internal_routes.py` | create | Verify location resolve endpoint behavior |

## Risks
- Kafka client APIs may differ from assumptions; implementation must stay consistent with the installed library surface.
- Hard readiness gates can make existing tests fail until every dependency is explicitly stubbed.
- Converting tests from `create_all()` to Alembic may expose latent fixture coupling and ordering issues.
- Fleet validation is client-only in this repo; the server contract can still block rollout outside the codebase.
- Dirty existing changes in the worktree may overlap with this task and must be respected while editing.

## Test Cases
- test that invalid body timezone returns `422 application/problem+json`
- test that invalid query timezone returns `422 application/problem+json`
- test that non-admin `X-Actor-Type` cannot mutate trips and returns `422`
- test that removed import/export endpoints return exact `404`
- test that admin create idempotency replay preserves original `ETag`
- test that duplicate `trip_no` conflict returns `409 TRIP_TRIP_NO_CONFLICT`
- test that duplicate telegram slip conflict returns a stable `409`
- test that a second empty-return for the same base trip is blocked by the database-backed contract
- test that terminal READY/SKIPPED enrichment retry returns the dedicated `409`
- test that max-attempt FAILED enrichments are not auto-claimed again
- test that manual retry can requeue a max-attempt FAILED enrichment
- test that outbox first failure backs off `5s` and dead-letters at configured ceiling
- test that `/ready` returns `503` when any hard dependency probe fails
- test that driver statement returns only `COMPLETED` trips by default
- test that location-service internal resolve returns the active forward/reverse route on exact normalized match
- test that trip-service tests build schema from Alembic `upgrade head`

## Out of Scope
- Fleet-service endpoint implementation outside this repository
- A compatibility shim for removed Excel APIs
- Schema registry or non-JSON Kafka payload formats

## Completion Criterion
- Trip-service code enforces the locked contracts without reopening removed Excel/weather scope.
- Location-service provides the internal resolve endpoint trip-service depends on.
- Automated tests for the new behaviors pass in Docker-backed local execution, and test evidence is recorded with actual command output.
- Repository memory/task files accurately describe what changed, what remains risky, and how the next agent should continue if needed.

---

## Plan Revisions
Document every change to this plan. Do not silently deviate.

### [2026-03-27] Allow trip-service lockfile updates
What changed:
- Added `services/trip-service/uv.lock` to the allowed file list.
Why:
- The task changes runtime dependencies (`tzdata`, `confluent-kafka`) and local `uv` commands may legitimately update the lockfile during verification.

### [2026-03-27] Document the expanded trip-service env surface
What changed:
- Added `services/trip-service/.env.example` to the allowed file list.
Why:
- Broker, readiness, and dependency settings changed; the example env file must stay aligned with runtime config.
