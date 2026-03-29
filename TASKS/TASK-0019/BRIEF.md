# BRIEF.md

## Objective
Harden Location Service for real production use by closing the current P0/P1 runtime, auth, readiness, provider, contract, and integration gaps, and align Trip Service's Location dependency handling to the tightened contract.

## In Scope
- Location Service auth, prod validation, readiness, docs gating, global problem+json behavior, ETag/If-Match completion, approval endpoint unification, provider config/runtime fixes, and startup processing-run recovery.
- Trip Service changes only where needed to authenticate to Location Service and classify Location business errors correctly.
- Smoke harness updates for offline and live provider verification.
- Task and memory records for TASK-0019.

## Out of Scope
- P2 cleanup from the severity plan: dead schema/model/error cleanup, persistent worker redesign, full observability cleanup, and taxonomy normalization.
- Trip Service public API changes.
- New service design work.

## Success Criteria
- Location Service route calculation succeeds against live Mapbox responses.
- Location Service no longer exposes unauthenticated non-health endpoints in prod.
- Readiness returns 503 when not ready.
- Trip Service distinguishes Location business-invalid responses from dependency failures.
- Offline smoke and live provider smoke both pass and are recorded.
