# BRIEF.md

## Task ID
TASK-0034

## Task Name
Trip/Location Full Production Readiness

## Phase
Phase 7 - Production Ready

## Primary Purpose
Turn `trip-service` and `location-service` into a release-gated production package with split worker topology, full-stack Compose deployment assets, CI gates, smoke/soak automation, and ops runbooks.

## Expected Outcome
- Trip and Location runtimes run as split API/worker processes.
- Both services expose internal-only `/metrics` endpoints and readiness covers all required workers.
- Location processing is handled by a durable DB-claimed worker loop instead of in-process background dispatch.
- Full-stack Compose assets exist for prod and CI verification, including ingress, Prometheus, and Grafana.
- Smoke, soak, backup, and restore automation are repo-owned and reusable outside old task folders.
- GitHub Actions verify and prod-gate workflows exist and enforce live-provider proof.

## In Scope
- TASK-0034 scaffolding and memory updates.
- Trip runtime split, health/metrics updates, and related tests.
- Location worker redesign, migration/env hardening, observability/metrics updates, and related tests.
- Full-stack Compose packaging, ops automation, CI workflows, and runbooks.
- Verification evidence for targeted tests and the new prod assets.

## Out of Scope
- Fleet service implementation or bundling it into the production stack.
- Changing public business API paths or auth domains.
- Redpanda backup automation beyond documented host-level snapshot procedure.
- Kubernetes/Helm deployment assets.

## Dependencies
- Existing TASK-0033 audit remediation worktree.
- Docker Compose v2, PostgreSQL, Redpanda, Prometheus, Grafana, and Nginx packaging inside the repo.
- Existing Mapbox/ORS abstractions and smoke/load scripts from previous tasks.

## Notes for the Agent
- Keep TASK-0034 separate from TASK-0033; do not reopen TASK-0033 scope.
- Full release scope is locked: full-stack Compose, GitHub Actions gates, always-live provider proof, internal `/metrics`, split worker topology, bundled reverse proxy and monitoring.
