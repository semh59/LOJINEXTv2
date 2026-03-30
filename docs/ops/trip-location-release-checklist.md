# Trip/Location — Release Checklist

Use this checklist for every release to production.

## Pre-Flight

- [ ] All PR checks pass (lint, type-check, tests)
- [ ] `MEMORY/PROJECT_STATE.md` reflects current state
- [ ] No open blockers in `MEMORY/PROJECT_STATE.md`
- [ ] `.env` file has production-grade secrets (non-default JWT secrets, real API keys)
- [ ] `TRIP_BROKER_TYPE=kafka` is explicitly set
- [ ] `TRIP_ALLOW_PLAINTEXT_IN_PROD` is `false` (or SASL is configured)
- [ ] Database backup taken before deployment

## Migration

- [ ] Trip migrations: `alembic upgrade head` completes without error
- [ ] Location migrations: `alembic upgrade head` completes without error
- [ ] Schema state matches expectations (no pending migrations)

## Deploy

- [ ] Build images: `docker compose -f docker-compose.prod.yml build`
- [ ] Start stack: `docker compose -f docker-compose.prod.yml up -d`
- [ ] Wait for health checks to stabilize (30–60s)

## Verify

- [ ] Trip `/health` returns 200
- [ ] Location `/health` returns 200
- [ ] Trip `/ready` returns 200 (all workers heartbeating)
- [ ] Location `/ready` returns 200 (processing worker heartbeating, providers live)
- [ ] Trip `/metrics` returns Prometheus payload with `trip_created_total`
- [ ] Location `/metrics` returns Prometheus payload with `location_processing_runs_total`
- [ ] Smoke test passes: `python ops/trip_location/smoke_stack.py`
- [ ] Grafana dashboard loads and shows data

## Rollback Plan

If any verification step fails:

1. Collect logs: `docker compose logs --tail=200 > /tmp/release-failure.log`
2. Stop the new deployment: `docker compose stop`
3. Restore previous images: `docker compose up -d` (with previous tag)
4. If migration was run: restore from pre-deployment backup (see backup-restore runbook)
5. File incident report

## Post-Release

- [ ] Monitor Grafana dashboard for 30 minutes
- [ ] Check for error spikes in logs
- [ ] Update `MEMORY/PROJECT_STATE.md` with release status
