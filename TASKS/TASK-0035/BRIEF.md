# BRIEF.md

## Task ID
TASK-0035

## Task Name
Audit Remediation Phase 1: Readiness and Documentation

## Phase
Phase 1 - Make readiness truthful

## Primary Purpose
Implement the first phase of the production audit remediation, focusing on architectural alignment (ADR), heartbeat persistence, and truthful readiness probes.

## Expected Outcome
- ADR-001 (Fleet V1 validation architecture) is written and locked.
- Fleet readiness policy is decided and documented.
- Trip and Location heartbeats are moved from /tmp to DB-backed storage.
- Health checks are switched from /health to /ready in release gates and smoke tests.
- Split-topology compose smoke test passes with the new readiness model.

## In Scope
- Documentation: ADR-001, Fleet readiness policy in MEMORY/DECISIONS.md.
- Code (Trip/Location): Heartbeat storage migration from /tmp to DB.
- Configuration: Update Docker Compose and CI/CD workflows to use /ready.
- Verification: Smoke test execution on split topology.

## Out of Scope
- Phase 2 and Phase 3 items from the audit (Driver runtime blockers, contract debt).
- Changing business logic beyond readiness/heartbeat infrastructure.

## Dependencies
- lojinext_full_production_audit_2026-04-01_revised.md (Audit Report)
