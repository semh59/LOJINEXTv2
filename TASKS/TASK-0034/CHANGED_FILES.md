# CHANGED_FILES.md

Track every file touched by TASK-0034. Keep this list current.

## Planned Touches

- `MEMORY/PROJECT_STATE.md`
- `MEMORY/DECISIONS.md`
- `TASKS/TASK-0034/BRIEF.md`
- `TASKS/TASK-0034/PLAN.md`
- `TASKS/TASK-0034/STATE.md`
- `TASKS/TASK-0034/CHANGED_FILES.md`
- `TASKS/TASK-0034/TEST_EVIDENCE.md`
- `TASKS/TASK-0034/NEXT_AGENT.md`
- `TASKS/TASK-0034/DONE_CHECKLIST.md`
- `deploy/compose/trip-location/docker-compose.prod.yml`
- `deploy/compose/trip-location/docker-compose.ci.yml`
- `deploy/compose/trip-location/.env.example`
- `deploy/compose/trip-location/init-db.sh`
- `deploy/compose/trip-location/nginx/nginx.conf.template`
- `deploy/compose/trip-location/prometheus/prometheus.yml`
- `deploy/compose/trip-location/grafana/provisioning/datasources/prometheus.yml`
- `deploy/compose/trip-location/grafana/provisioning/dashboards/dashboards.yml`
- `deploy/compose/trip-location/grafana/dashboards/trip-location-overview.json`
- `ops/trip_location/smoke_stack.py`
- `ops/trip_location/soak_e2e.py`
- `ops/trip_location/backup_postgres.py`
- `ops/trip_location/restore_postgres.py`
- `.github/workflows/trip-location-verify.yml`
- `.github/workflows/trip-location-prod-gate.yml`
- `docs/ops/trip-location-production.md`
- `docs/ops/trip-location-release-checklist.md`
- `docs/ops/trip-location-incidents.md`
- `docs/ops/trip-location-backup-restore.md`

## Actual Touches

- `TASKS/TASK-0034/BRIEF.md` (created by previous Codex session)
- `TASKS/TASK-0034/PLAN.md` (created by previous Codex session, updated this session)
- `TASKS/TASK-0034/STATE.md` (created by previous Codex session, updated this session)
- `TASKS/TASK-0034/CHANGED_FILES.md` (created by previous Codex session, updated this session)
- `TASKS/TASK-0034/TEST_EVIDENCE.md` (created by previous Codex session, updated this session)
- `TASKS/TASK-0034/NEXT_AGENT.md` (created by previous Codex session, updated this session)
- `TASKS/TASK-0034/DONE_CHECKLIST.md` (created by previous Codex session, updated this session)
- `MEMORY/PROJECT_STATE.md` (updated this session)
- `MEMORY/DECISIONS.md` (updated by previous Codex session)
- `deploy/compose/trip-location/docker-compose.prod.yml` (created)
- `deploy/compose/trip-location/docker-compose.ci.yml` (created)
- `deploy/compose/trip-location/.env.example` (created)
- `deploy/compose/trip-location/init-db.sh` (created)
- `deploy/compose/trip-location/nginx/nginx.conf.template` (created)
- `deploy/compose/trip-location/prometheus/prometheus.yml` (created)
- `deploy/compose/trip-location/grafana/provisioning/datasources/prometheus.yml` (created)
- `deploy/compose/trip-location/grafana/provisioning/dashboards/dashboards.yml` (created)
- `deploy/compose/trip-location/grafana/dashboards/trip-location-overview.json` (created)
- `ops/trip_location/smoke_stack.py` (created)
- `ops/trip_location/soak_e2e.py` (created)
- `ops/trip_location/backup_postgres.py` (created)
- `ops/trip_location/restore_postgres.py` (created)
- `.github/workflows/trip-location-verify.yml` (created)
- `.github/workflows/trip-location-prod-gate.yml` (created)
- `docs/ops/trip-location-production.md` (created)
- `docs/ops/trip-location-release-checklist.md` (created)
- `docs/ops/trip-location-incidents.md` (created)
- `docs/ops/trip-location-backup-restore.md` (created)

## Not Touched (Steps 2-3 already done by TASK-0033)

The following files were in the original plan but were NOT modified because they were already complete:

- `services/trip-service/src/trip_service/main.py` — Already decoupled
- `services/trip-service/src/trip_service/entrypoints/api.py` — Already exists
- `services/trip-service/src/trip_service/entrypoints/enrichment_worker.py` — Already exists
- `services/trip-service/src/trip_service/entrypoints/outbox_worker.py` — Already exists
- `services/trip-service/src/trip_service/entrypoints/cleanup_worker.py` — Already exists
- `services/trip-service/src/trip_service/routers/health.py` — Already has /metrics and heartbeat hard-gates
- `services/trip-service/pyproject.toml` — Already has split scripts
- `services/location-service/src/location_service/main.py` — Already decoupled
- `services/location-service/src/location_service/processing/worker.py` — Already has durable claim logic
- `services/location-service/src/location_service/entrypoints/api.py` — Already exists
- `services/location-service/src/location_service/entrypoints/processing_worker.py` — Already exists
- `services/location-service/src/location_service/worker_heartbeats.py` — Already exists
- `services/location-service/src/location_service/routers/health.py` — Already has /metrics and heartbeat hard-gates
- `services/location-service/alembic/env.py` — Already prefers Alembic config URL
- `services/location-service/pyproject.toml` — Already has split scripts
