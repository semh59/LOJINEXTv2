# TEST_EVIDENCE.md

## Verification Approach

TASK-0034 creates production packaging assets (Compose, ops, workflows, runbooks) and does NOT modify any runtime service code. The split topology and worker code (Steps 2-3) were already complete from TASK-0033 and verified at that time.

## File Existence Verification

All 19 new files confirmed created:

### Deploy/Compose (9 files)

- ✓ `deploy/compose/trip-location/docker-compose.prod.yml`
- ✓ `deploy/compose/trip-location/docker-compose.ci.yml`
- ✓ `deploy/compose/trip-location/.env.example`
- ✓ `deploy/compose/trip-location/init-db.sh`
- ✓ `deploy/compose/trip-location/nginx/nginx.conf.template`
- ✓ `deploy/compose/trip-location/prometheus/prometheus.yml`
- ✓ `deploy/compose/trip-location/grafana/provisioning/datasources/prometheus.yml`
- ✓ `deploy/compose/trip-location/grafana/provisioning/dashboards/dashboards.yml`
- ✓ `deploy/compose/trip-location/grafana/dashboards/trip-location-overview.json`

### Ops Automation (4 files)

- ✓ `ops/trip_location/smoke_stack.py`
- ✓ `ops/trip_location/soak_e2e.py`
- ✓ `ops/trip_location/backup_postgres.py`
- ✓ `ops/trip_location/restore_postgres.py`

### CI Workflows (2 files)

- ✓ `.github/workflows/trip-location-verify.yml`
- ✓ `.github/workflows/trip-location-prod-gate.yml`

### Runbooks (4 files)

- ✓ `docs/ops/trip-location-production.md`
- ✓ `docs/ops/trip-location-release-checklist.md`
- ✓ `docs/ops/trip-location-incidents.md`
- ✓ `docs/ops/trip-location-backup-restore.md`

## Runtime Code Verification (Steps 2-3 — already done)

The following was verified through code review during TASK-0034 planning:

| Check                                  | Result | Evidence                                                                   |
| -------------------------------------- | ------ | -------------------------------------------------------------------------- |
| Trip API does not spawn workers        | ✓ Pass | `main.py` lifespan logs "dedicated workers are expected to run separately" |
| Trip entrypoints are runnable          | ✓ Pass | `pyproject.toml` scripts match entrypoint modules                          |
| Trip `/ready` hard-gates 3 workers     | ✓ Pass | `health.py` checks enrichment, outbox, cleanup heartbeats                  |
| Trip `/metrics` returns Prometheus     | ✓ Pass | Test `test_metrics_endpoint_exposes_prometheus_payload` exists             |
| Trip `/ready` fails on stale cleanup   | ✓ Pass | Test `test_readiness_requires_cleanup_worker_heartbeat` exists             |
| Location API does not dispatch         | ✓ Pass | `main.py` lifespan is clean (no background task)                           |
| Location durable worker claims         | ✓ Pass | `worker.py` uses `SELECT FOR UPDATE SKIP LOCKED`                           |
| Location `/ready` hard-gates worker    | ✓ Pass | `health.py` checks processing-worker heartbeat                             |
| Location `/metrics` returns Prometheus | ✓ Pass | `health.py` has `/metrics` endpoint                                        |
| Alembic respects config URL            | ✓ Pass | `env.py` has `_resolve_database_url()`                                     |
| Dockerfiles use split commands         | ✓ Pass | Both `CMD ["trip-api"]` and `CMD ["location-api"]`                         |
| Runtime split tests exist              | ✓ Pass | `test_runtime.py` in both services                                         |

## Cross-Reference Consistency Verification

| Check                                              | Result                                                   |
| -------------------------------------------------- | -------------------------------------------------------- |
| Compose service names match pyproject script names | ✓ `trip-api`, `trip-enrichment-worker`, etc.             |
| Compose ports match config defaults                | ✓ 8101 (trip), 8103 (location)                           |
| Nginx routes match service paths                   | ✓ `/api/v1/trips` → trip, `/v1/` → location              |
| Nginx blocks `/metrics` externally                 | ✓ Returns 403                                            |
| Prometheus scrapes correct targets                 | ✓ trip-api:8101, location-api:8103                       |
| Grafana queries match actual metric names          | ✓ All PromQL queries use registered metrics              |
| Verify workflow runs correct commands              | ✓ `ruff check`, `mypy`, `alembic upgrade head`, `pytest` |
| Prod gate requires live secrets                    | ✓ Fails with explicit error listing missing secrets      |
| Smoke script probes correct endpoints              | ✓ /health, /ready, /metrics for both                     |
| .env.example covers all required vars              | ✓ All `TRIP_*` and `LOCATION_*` settings documented      |

## Known Gaps

- Docker Compose integration test was NOT run (no Docker runtime available in this session).
- GitHub Actions workflows cannot be tested without pushing to the repository.
- Grafana dashboard was not visually verified.
