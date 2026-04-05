# NEXT_AGENT.md

## Task Goal
Restore truthful repo memory and a working Trip/Fleet/Driver live-contract baseline that later runtime and auth tasks can safely build on.

## What Was Done
- Created the full `TASK-0045` task record set.
- Corrected `MEMORY/PROJECT_STATE.md` so the repo no longer claims a nonexistent completed `TASK-0044`.
- Repaired Trip live-contract/auth edges:
  - generic `POST /internal/v1/assets/reference-check`
  - legacy `GET /internal/v1/trips/driver-check/{driver_id}` compatibility
  - outbound Fleet bearer auth
  - Fleet response compatibility parsing
  - reference endpoint allowlist for `driver-service` and `fleet-service`
- Repaired Fleet live-contract/auth edges:
  - real Driver eligibility endpoint
  - real Trip asset reference endpoint
  - nullable Trip compatibility request handling
  - hard-delete wiring through Trip reference checks
  - test bootstrap and readiness heartbeat setup
  - naive-UTC timestamp normalization across the current schema's request/repo/worker paths
- Repaired Driver live-contract/auth edges:
  - `SERVICE` role internal token generation
  - internal service allowlist enforcement
  - broker-aware readiness gating
  - smoke/readiness tests that use the runtime-patched DB factory instead of stale module-level bindings
- Recorded the temporary `PLATFORM_JWT_SECRET` bridge in `MEMORY/DECISIONS.md`.
- Recorded the open Fleet `initial_spec` create-gap in `MEMORY/KNOWN_ISSUES.md`.
- Verified final targeted Trip/Fleet/Driver suites. See `TEST_EVIDENCE.md`.

## What Is Not Done Yet
1. Create the git commit/push handoff for `TASK-0045`.
2. Decide whether to mark `TASK-0045` ready for review or to keep it open for any last repo-truth cleanup the human wants.
3. Start the next recovery slice (`TASK-0046+`) for the broader roadmap: runtime promotion, auth package extraction, and `identity-service`.
4. Address `ISSUE-003` if the Fleet inline `initial_spec` create contract must actually work instead of requiring a follow-up spec-version call.

## First Action
Read `TASKS/TASK-0045/TEST_EVIDENCE.md`, review `git diff`, then either commit `TASK-0045` as the recovery baseline or open the next task for the broader recovery roadmap.

## Critical Files Beyond The Standard Read Order
- `MEMORY/DECISIONS.md`
- `MEMORY/KNOWN_ISSUES.md`
- `services/fleet-service/src/fleet_service/timestamps.py`
- `services/trip-service/src/trip_service/routers/trips.py`
- `services/trip-service/src/trip_service/dependencies.py`
- `services/fleet-service/src/fleet_service/clients/driver_client.py`
- `services/fleet-service/src/fleet_service/clients/trip_client.py`
- `services/driver-service/src/driver_service/auth.py`
- `services/driver-service/src/driver_service/routers/__init__.py`

## Risks And Traps
- `PLATFORM_JWT_SECRET` is temporary recovery glue only. Do not treat it as the final auth design.
- The Fleet schema still stores naive UTC timestamps. The new `fleet_service.timestamps` helper must be used for any new Fleet write/comparison path until a schema migration changes that assumption.
- `services/driver-service/uv.lock` is dirty in the worktree and was intentionally left untouched.
- Driver final verification used `services/driver-service/.venv` because the workstation's global Python lacks `phonenumbers`.

## Open Human Decisions
- None discovered in this task.

## Remaining Done Condition
- For `TASK-0045` itself: commit/push handoff only.
- For the larger roadmap: continue with the next tasks rather than quietly extending `TASK-0045`.

## Temporary Implementations
- `PLATFORM_JWT_SECRET` bridge in Trip/Fleet/Driver config/auth paths.
- Fleet naive-UTC normalization helper in `services/fleet-service/src/fleet_service/timestamps.py` to match the current schema until a future schema/auth cleanup task changes it.
