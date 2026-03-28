# BRIEF.md

## Task
TASK-0013 — Location-Service Fixes After Deep Audit

## Goal
Fix the location-service failures and lint debt identified in TASK-0012, then re-run the full test matrix to restore green status.

## Out of Scope
- New product features or contract changes not covered by TASK-0012 findings.
- Trip-service changes, unless a location-service fix requires a coordinated change explicitly confirmed by tests.

## Success Criteria
- `ruff check src tests` passes in `services/location-service`.
- `pytest` passes in `services/location-service`.
- Docker smoke stack still passes.

