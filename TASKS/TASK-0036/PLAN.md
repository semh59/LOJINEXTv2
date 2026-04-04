# PLAN.md

## Objective

Finalize Fleet Service implementation from Phase D through Phase H (Test Matrix).

## How I Understand the Problem

The Fleet Service needs to reach production readiness by implementing spec versioning, trailer mirroring, internal APIs for S2S communication, a robust outbox relay worker, and a comprehensive test matrix. I have already completed Phases D-G and now need to document them formally and proceed to Phase H.

## Approach

1. [DONE] Phase D: Implement Vehicle Spec Versions (3 endpoints).
2. [DONE] Phase E: Implement Trailer Mirror (12 endpoints).
3. [DONE] Phase F: Implement Internal Service APIs (7 endpoints).
4. [DONE] Phase G: Implement Outbox Worker & Readiness (3 loops, 2 probes).
5. [TODO] Phase H: Implement Test Matrix (conftest + unit/integration/contract tests).

## Files That Will Change

| File                                                  | Action | Why                |
| ----------------------------------------------------- | ------ | ------------------ |
| `src/fleet_service/repositories/vehicle_spec_repo.py` | create | Phase D            |
| `src/fleet_service/services/vehicle_spec_service.py`  | create | Phase D            |
| `src/fleet_service/routers/vehicle_spec_router.py`    | create | Phase D            |
| `src/fleet_service/repositories/trailer_repo.py`      | create | Phase E            |
| `src/fleet_service/repositories/trailer_spec_repo.py` | create | Phase E            |
| `src/fleet_service/services/trailer_service.py`       | create | Phase E            |
| `src/fleet_service/routers/trailer_router.py`         | create | Phase E            |
| `src/fleet_service/clients/driver_client.py`          | create | Phase F            |
| `src/fleet_service/clients/trip_client.py`            | create | Phase F            |
| `src/fleet_service/services/internal_service.py`      | create | Phase F            |
| `src/fleet_service/routers/internal_router.py`        | create | Phase F            |
| `src/fleet_service/broker.py`                         | create | Phase G            |
| `src/fleet_service/workers/outbox_relay.py`           | create | Phase G            |
| `src/fleet_service/worker_heartbeats.py`              | create | Phase G            |
| `src/fleet_service/entrypoints/worker.py`             | modify | Phase G loops      |
| `src/fleet_service/routers/health.py`                 | modify | Phase G readiness  |
| `tests/conftest.py`                                   | create | Phase H foundation |
| `tests/test_unit.py`                                  | create | Phase H            |
| `tests/test_integration.py`                           | create | Phase H            |

## Risks

- Concurrency issues in Outbox relay (mitigated by SKIP LOCKED).
- Auth mismatch in internal APIs (checked against specification).

## Test Cases

- test_vehicle_spec_versioning: create new spec, verify current vs historic.
- test_trailer_crud: happy path for all endpoints.
- test_outbox_relay: insert row, worker publishes, row marked published.
- test_readiness_probe: returns error if DB down or heartbeat stale.

## Completion Criterion

- All 33 endpoints functional and tested.
- Outbox relay processing events correctly.
- Readiness probe reflecting system health.
- All tests in green.
