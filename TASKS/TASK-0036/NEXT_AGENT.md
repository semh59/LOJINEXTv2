# NEXT_AGENT.md

## Where We Stopped

Phases D, E, F, and G are implemented and verified via deep audit and lint.

## What is Done

- Vehicle Spec Versions (D)
- Trailer Mirror (E)
- Internal S2S APIs (F)
- Outbox relay, heartbeats, and production readiness (G)

## What is Next

Phase H: Test Matrix Implementation.

- Need to create `tests/conftest.py` with TestContainers PostgreSQL.
- Need to implement Unit and Integration tests for Fleet Service.
- Need to verify all endpoints against the contract.

## Context Needed

- Refer to `driver-service/tests/conftest.py` for the fixture pattern.
- Fleet service uses `ActorType.ADMIN`, `ActorType.SUPER_ADMIN`, and `ActorType.SERVICE` for auth.
- Outbox relay should be tested with mocked broker.

## Open Risks

- Schema migrations for new tables (VehicleSpec, Trailer, TrailerSpec, etc.) must be verified in a real DB environment.
