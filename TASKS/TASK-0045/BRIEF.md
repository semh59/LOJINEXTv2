# BRIEF.md

## Task ID
TASK-0045

## Task Name
Recovery Phase 1: Repo Truth and Live Contract Repair

## Phase
Phase 7 - Production Recovery

## Primary Purpose
Restore truthful repository memory and a working live Trip/Fleet/Driver contract baseline that later runtime and auth migrations can safely build on.

## Expected Outcome
- `MEMORY/PROJECT_STATE.md` reflects the actual repo/task state and no longer claims a missing `TASK-0044` as completed.
- `trip-service` no longer crashes in `GET /internal/v1/trips/driver-check/{driver_id}` and exposes `POST /internal/v1/assets/reference-check` for `DRIVER`, `VEHICLE`, and `TRAILER`.
- `trip-service` calls Fleet validation with service bearer auth and accepts both the current and repaired Fleet response shapes during the transition.
- `fleet-service` validates Trip references against the real Driver eligibility contract, accepts `vehicle_id=null` for fallback trip ingest, and uses Trip reference checks in hard-delete flows.
- `driver-service` Trip-reference maintenance calls use `role=SERVICE` tokens accepted by Trip and `/ready` returns `503` when DB or worker heartbeat checks fail.

## In Scope
- Create full `TASKS/TASK-0045/` task records and update repository memory to match the actual repo state.
- Repair the live inter-service contract and auth edges across `trip-service`, `fleet-service`, and `driver-service`.
- Add targeted regression tests for the repaired contracts and readiness behavior.
- Document the recovery-time shared HS256 bridge in the service env examples if the code introduces it.

## Out of Scope
- `packages/platform-auth`
- `services/identity-service`
- Four-service compose/runtime promotion and CI workflow expansion
- Full Fleet test-matrix remediation beyond the contract slices touched here
- Location Service feature changes

## Dependencies
- `MEMORY/DECISIONS.md`
- `MEMORY/KNOWN_ISSUES.md`
- Existing Trip/Fleet/Driver service code and tests

## Notes for the Agent
- Keep the scope to the recovery baseline only; later auth/runtime tasks stay separate.
- Do not touch unrelated user changes, including the existing dirty `services/driver-service/uv.lock`.
