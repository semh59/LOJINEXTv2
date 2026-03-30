# PLAN.md

## Objective

Turn `trip-service` and `location-service` into a release-gated production package with split API/worker topology, durable worker orchestration, full-stack Compose assets, CI gates, ops automation, and runbooks.

## How I Understand the Problem

`TASK-0033` closed current correctness gaps, but both services still run with development-shaped topology and repo-scattered operational tooling. The remaining work is production packaging: separate long-running workers from API lifecycles, expose internal-only metrics, hard-gate readiness on critical workers, move Location processing onto claimed worker execution, harden Alembic for CI/release use, and bundle deploy/observe/verify assets directly in the repository.

## Approach

1. Register `TASK-0034` in repository memory and keep a full task ledger under `TASKS/TASK-0034/`.
2. Split Trip Service into API plus dedicated enrichment/outbox/cleanup entrypoints, with readiness/metrics coverage.
3. Move Location processing to a claimed worker loop, add worker readiness/metrics, and fix Alembic runtime expectations.
4. Add full-stack Compose assets, permanent smoke/soak/backup/restore tooling, and release-gated GitHub workflows.
5. Add ops runbooks and verify targeted tests plus the new prod assets.

## Files That Will Change

Nothing outside this list gets touched.
New file needed during build -> update this list first.

| File                                                                              | Action | Why                                                                             |
| --------------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------------------- |
| `MEMORY/PROJECT_STATE.md`                                                         | modify | Mark TASK-0034 active and advance task counter                                  |
| `MEMORY/DECISIONS.md`                                                             | modify | Record the production-readiness packaging decisions                             |
| `TASKS/TASK-0034/BRIEF.md`                                                        | create | Task definition                                                                 |
| `TASKS/TASK-0034/PLAN.md`                                                         | create | Execution plan                                                                  |
| `TASKS/TASK-0034/STATE.md`                                                        | create | Progress ledger                                                                 |
| `TASKS/TASK-0034/CHANGED_FILES.md`                                                | create | File ledger                                                                     |
| `TASKS/TASK-0034/TEST_EVIDENCE.md`                                                | create | Verification evidence                                                           |
| `TASKS/TASK-0034/NEXT_AGENT.md`                                                   | create | Handoff notes                                                                   |
| `TASKS/TASK-0034/DONE_CHECKLIST.md`                                               | create | Completion checklist                                                            |
| `services/trip-service/src/trip_service/main.py`                                  | modify | Remove worker spawning from API lifespan                                        |
| `services/trip-service/src/trip_service/entrypoints/api.py`                       | create | API entrypoint                                                                  |
| `services/trip-service/src/trip_service/entrypoints/enrichment_worker.py`         | create | Enrichment worker entrypoint                                                    |
| `services/trip-service/src/trip_service/entrypoints/outbox_worker.py`             | create | Outbox worker entrypoint                                                        |
| `services/trip-service/src/trip_service/entrypoints/cleanup_worker.py`            | create | Cleanup worker entrypoint                                                       |
| `services/trip-service/src/trip_service/routers/health.py`                        | modify | Add cleanup worker readiness and `/metrics`                                     |
| `services/trip-service/src/trip_service/observability.py`                         | modify | Cleanup heartbeat support                                                       |
| `services/trip-service/src/trip_service/worker_heartbeats.py`                     | modify | Worker heartbeat helpers if needed                                              |
| `services/trip-service/pyproject.toml`                                            | modify | Add runnable entrypoint scripts                                                 |
| `services/trip-service/tests/test_contract.py`                                    | modify | Health/metrics regression coverage                                              |
| `services/location-service/src/location_service/main.py`                          | modify | Remove in-process processing dispatch from API lifespan, enable logging/metrics |
| `services/location-service/src/location_service/processing/pipeline.py`           | modify | Stop API-side background dispatch and support claimed worker execution          |
| `services/location-service/src/location_service/processing/worker.py`             | create | Durable processing worker loop                                                  |
| `services/location-service/src/location_service/entrypoints/api.py`               | create | API entrypoint                                                                  |
| `services/location-service/src/location_service/entrypoints/processing_worker.py` | create | Processing worker entrypoint                                                    |
| `services/location-service/src/location_service/worker_heartbeats.py`             | create | Worker heartbeat helpers                                                        |
| `services/location-service/src/location_service/models.py`                        | modify | Add processing-run claim fields                                                 |
| `services/location-service/alembic/versions/<revision>_processing_run_claims.py`  | create | Add processing-run claim columns/index support                                  |
| `services/location-service/src/location_service/config.py`                        | modify | Add processing worker config                                                    |
| `services/location-service/src/location_service/routers/health.py`                | modify | Add processing-worker readiness and `/metrics`                                  |
| `services/location-service/src/location_service/middleware.py`                    | modify | Add pure ASGI Prometheus middleware                                             |
| `services/location-service/src/location_service/observability.py`                 | modify | Structured logging + request metrics helpers                                    |
| `services/location-service/alembic/env.py`                                        | modify | Prefer Alembic config DB URL                                                    |
| `services/location-service/pyproject.toml`                                        | modify | Add runnable entrypoint scripts                                                 |
| `services/location-service/tests/test_processing_flow.py`                         | modify | Worker topology/claim tests                                                     |
| `services/location-service/tests/test_schema_integration.py`                      | modify | Readiness/metrics tests                                                         |
| `services/location-service/tests/test_migrations.py`                              | modify | Processing-run claim migration coverage                                         |
| `services/location-service/tests/conftest.py`                                     | modify | Testing helpers for worker topology                                             |
| `deploy/compose/trip-location/docker-compose.prod.yml`                            | create | Full production stack definition                                                |
| `deploy/compose/trip-location/docker-compose.ci.yml`                              | create | CI-friendly overlay                                                             |
| `deploy/compose/trip-location/.env.example`                                       | create | Stack env surface                                                               |
| `deploy/compose/trip-location/init-db.sh`                                         | create | Multi-database init script                                                      |
| `deploy/compose/trip-location/nginx/nginx.conf.template`                          | create | Reverse proxy rules                                                             |
| `deploy/compose/trip-location/prometheus/prometheus.yml`                          | create | Prometheus scrape config                                                        |
| `deploy/compose/trip-location/grafana/provisioning/datasources/prometheus.yml`    | create | Grafana datasource provisioning                                                 |
| `deploy/compose/trip-location/grafana/provisioning/dashboards/dashboards.yml`     | create | Grafana dashboard provisioning                                                  |
| `deploy/compose/trip-location/grafana/dashboards/trip-location-overview.json`     | create | Overview dashboard                                                              |
| `ops/trip_location/smoke_stack.py`                                                | create | Permanent smoke utility                                                         |
| `ops/trip_location/soak_e2e.py`                                                   | create | End-to-end soak utility                                                         |
| `ops/trip_location/backup_postgres.py`                                            | create | Logical backup utility                                                          |
| `ops/trip_location/restore_postgres.py`                                           | create | Restore utility                                                                 |
| `.github/workflows/trip-location-verify.yml`                                      | create | PR/branch verification gate                                                     |
| `.github/workflows/trip-location-prod-gate.yml`                                   | create | Release/live verification gate                                                  |
| `docs/ops/trip-location-production.md`                                            | create | Production deployment runbook                                                   |
| `docs/ops/trip-location-release-checklist.md`                                     | create | Release checklist                                                               |
| `docs/ops/trip-location-incidents.md`                                             | create | Incident runbooks                                                               |
| `docs/ops/trip-location-backup-restore.md`                                        | create | Backup/restore runbook                                                          |

## Risks

- Split worker topology can break existing local startup assumptions if entrypoints or Docker commands drift from package install metadata.
- Location processing claim logic must avoid double-claiming stale runs and must keep provider calls outside DB transactions.
- Compose assets can become misleading if they are not aligned with actual env names, readiness paths, and migration steps.
- The prod-gate workflow intentionally requires live provider secrets and will fail hard when they are missing; that is by design.

## Test Cases

- Trip API startup does not spawn workers; dedicated entrypoints do.
- Trip `/ready` fails when cleanup heartbeat is stale and `/metrics` returns Prometheus output.
- Location API startup does not dispatch queued runs; worker loop claims queued/stale runs and completes them.
- Location `/ready` fails when processing worker heartbeat is stale and `/metrics` returns Prometheus output.
- Location Alembic env accepts explicit `sqlalchemy.url` without depending on runtime env defaults.
- Processing-run claim migration upgrades cleanly and exposes new claim columns.
- Compose/ops assets reference the split topology and hard dependency order consistently.

## Out of Scope

- Fleet service implementation or shipping it inside the production stack.
- Kubernetes/Helm packaging.
- Changing public business API paths, auth domains, or downstream payload contracts.

## Completion Criterion

TASK-0034 is complete when split runtimes, Location claimed worker execution, production compose/ops/workflow assets, and targeted verification evidence all exist and repository memory reflects the new production packaging state.

---

## Plan Revisions

Document every change to this plan. Do not silently deviate.

### [2026-03-30] Initial task plan

What changed: Created TASK-0034 as the explicit full production-readiness packaging task.
Why: The requested work extends beyond correctness fixes into release topology, deployment assets, and operational verification.

### [2026-03-30] Steps 2-3 already completed by TASK-0033

What changed: Deep analysis revealed that Steps 2-3 (Trip split topology, Location durable worker) were already fully implemented during TASK-0033. The original plan incorrectly assumed these were pending.
Why: The first agent only created task scaffolding and did not perform a deep codebase analysis before writing the plan. All split entrypoints, health/metrics, worker heartbeats, pyproject scripts, Dockerfiles, and runtime tests already existed in HEAD.
Impact: Steps 2-3 skipped. Implementation focused on Steps 4-5 (deploy/ops/workflows/runbooks + verification).

### [2026-03-30] Added init-db.sh for multi-database PostgreSQL

What changed: Added `deploy/compose/trip-location/init-db.sh` to auto-create the `location_service` database on first PostgreSQL startup.
Why: The Compose stack uses a single PostgreSQL instance with two databases. The init script ensures both databases exist without manual intervention.
