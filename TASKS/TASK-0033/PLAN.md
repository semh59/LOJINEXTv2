# PLAN.md

## Objective
Deliver the remaining current-HEAD Trip and Location audit remediation so both services close the confirmed correctness gaps and ship the selected hardening defaults.

## How I Understand the Problem
The audit mixed still-valid defects with stale findings. Current HEAD still needs concrete fixes in Trip outbox persistence/reliability, Trip overlap/list/cancel/retry/hash behavior, shared Trip HTTP clients, Location live-pair uniqueness/filter semantics, Location route validation/segment metadata completeness, cached provider readiness, and normalization edge-case coverage. This task should implement only those active gaps and leave already-resolved findings alone.

## Approach
1. Create TASK-0033 records and update repository memory so the task and chosen defaults are explicit.
2. Fix Trip Service correctness issues, then add the shared client and worker/cleanup schema-not-ready hardening.
3. Fix Location Service pair uniqueness/filter behavior and provider/readiness/processing completeness.
4. Add regression coverage for the new logic and run targeted pytest suites for both services.
5. Record final evidence, changed files, and handoff notes.

## Files That Will Change
Nothing outside this list gets touched.
New file needed during build -> update this list first.

| File | Action | Why |
|------|--------|-----|
| `MEMORY/PROJECT_STATE.md` | modify | Register TASK-0033 as active work |
| `MEMORY/DECISIONS.md` | modify | Record the task split and selected remediation defaults |
| `TASKS/TASK-0033/BRIEF.md` | create | Task definition |
| `TASKS/TASK-0033/PLAN.md` | create | Execution plan |
| `TASKS/TASK-0033/STATE.md` | create | Progress tracking |
| `TASKS/TASK-0033/CHANGED_FILES.md` | create | File ledger |
| `TASKS/TASK-0033/TEST_EVIDENCE.md` | create | Test evidence |
| `TASKS/TASK-0033/NEXT_AGENT.md` | create | Handoff |
| `TASKS/TASK-0033/DONE_CHECKLIST.md` | create | Completion checklist |
| `services/trip-service/src/trip_service/models.py` | modify | Add outbox `last_error_code` parity |
| `services/trip-service/src/trip_service/workers/outbox_relay.py` | modify | Per-event publish commits and schema-not-ready handling |
| `services/trip-service/src/trip_service/trip_helpers.py` | modify | Advisory-lock overlap serialization |
| `services/trip-service/src/trip_service/routers/trips.py` | modify | List/cancel/hash/retry behavior fixes |
| `services/trip-service/src/trip_service/http_clients.py` | create | Shared HTTPX clients |
| `services/trip-service/src/trip_service/dependencies.py` | modify | Reuse shared dependency client |
| `services/trip-service/src/trip_service/workers/enrichment_worker.py` | modify | Reuse shared location client and schema-not-ready handling |
| `services/trip-service/src/trip_service/observability.py` | modify | Cleanup-loop schema-not-ready handling |
| `services/trip-service/src/trip_service/main.py` | modify | Close shared clients on shutdown |
| `services/trip-service/tests/test_workers.py` | modify | Outbox and retry regressions |
| `services/trip-service/tests/test_integration.py` | modify | Trip list/cancel/manual hash regressions |
| `services/trip-service/tests/test_migrations.py` | modify | ORM/schema parity smoke coverage |
| `services/location-service/src/location_service/models.py` | modify | Live-pair uniqueness index definition |
| `services/location-service/alembic/versions/4d2b8c9e7f10_route_pair_live_uniqueness.py` | create | Enforce non-deleted pair uniqueness |
| `services/location-service/src/location_service/errors.py` | modify | Invalid filter + integrity mapping helper |
| `services/location-service/src/location_service/routers/pairs.py` | modify | Filter semantics and integrity handling |
| `services/location-service/src/location_service/providers/mapbox_directions.py` | modify | Request steps for intersection metadata |
| `services/location-service/src/location_service/processing/pipeline.py` | modify | Validation summaries and segment metadata derivation |
| `services/location-service/src/location_service/config.py` | modify | Provider probe TTL/coordinate config |
| `services/location-service/src/location_service/provider_health.py` | create | Cached live provider probes |
| `services/location-service/src/location_service/routers/health.py` | modify | Cached provider readiness checks |
| `services/location-service/.env.example` | modify | Document readiness probe config |
| `services/location-service/tests/test_pairs_api.py` | modify | Pair filter and uniqueness regression coverage |
| `services/location-service/tests/test_processing_flow.py` | modify | Validation delta and segment metadata coverage |
| `services/location-service/tests/test_mock_pipeline.py` | modify | Mock pipeline metadata expectations |
| `services/location-service/tests/test_providers.py` | modify | Directions request contract coverage |
| `services/location-service/tests/test_schema_integration.py` | modify | Cached readiness behavior coverage |
| `services/location-service/tests/test_unit.py` | modify | Normalization edge cases |
| `services/location-service/tests/test_migrations.py` | create | Location migration smoke/regression coverage |

## Risks
- Trip per-event outbox commits may break existing worker tests if claim-token/session assumptions are wrong.
- Advisory locks must stay transaction-scoped and deterministic across driver/vehicle/trailer resources to avoid deadlocks.
- The new Location uniqueness migration can fail on existing duplicate live pairs; the migration must fail loudly and descriptively.
- Cached readiness probes must not hammer providers or incorrectly cache partial failures indefinitely.
- Mapbox step/intersection metadata can be sparse; the segment logic must degrade cleanly when fields are absent.

## Test Cases
- Test that Trip outbox failures persist `last_error_code` after commit.
- Test that Trip outbox publishes one successful row even when another row in the same batch fails.
- Test that `GET /api/v1/trips` hides soft-deleted rows by default but returns them when explicitly filtered.
- Test that canceling an already soft-deleted Trip with a stale ETag returns 412.
- Test that manual Trip create and empty-return create persist `source_payload_hash`.
- Test that manual enrichment retry resets attempt count to zero.
- Test that Location pair list defaults exclude soft-deleted rows, `is_active=false` returns drafts only, and contradictory filters return 422.
- Test that live-pair uniqueness violations map to 409 on create/update.
- Test that route validation writes PASS/WARNING/FAIL/UNVALIDATED with percent-point deltas.
- Test that segment metadata uses Mapbox intersections for road class, urban class, and tunnel flags.
- Test that `/ready` caches provider probes, reports probe age, and returns 503 for live provider failures.
- Test normalization of combining dotted-I and NFKC compatibility forms.

## Out of Scope
- TASK-0020 durable worker redesign.
- Stale audit items already fixed in current HEAD.
- Any public contract changes not explicitly listed in BRIEF.md.

## Completion Criterion
TASK-0033 is complete when the listed Trip and Location behaviors are implemented, the targeted pytest suites pass, and task evidence/records reflect the actual work performed.

---

## Plan Revisions
Document every change to this plan. Do not silently deviate.

### [2026-03-30] Initial task plan
What changed: Created TASK-0033 as a standalone current-HEAD audit remediation task.
Why: The requested work spans Trip and Location fixes that should not be folded into TASK-0020.
