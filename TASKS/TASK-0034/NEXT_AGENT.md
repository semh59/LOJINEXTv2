# NEXT_AGENT.md

## Current Snapshot

- TASK-0034 is complete and ready for review.
- All production packaging assets have been created: Compose stack, ops scripts, CI workflows, and runbooks.
- Steps 2-3 (split topology, durable workers) were already done by TASK-0033 and verified via code review.
- No runtime service code was modified by this task.

## What Was Built

| Category      | Files                                         | Description                                                          |
| ------------- | --------------------------------------------- | -------------------------------------------------------------------- |
| Compose Stack | 9 files under `deploy/compose/trip-location/` | Production and CI Compose, .env, init-db, nginx, prometheus, grafana |
| Ops Scripts   | 4 files under `ops/trip_location/`            | Smoke, soak, backup, restore (all Python, zero external deps)        |
| CI Workflows  | 2 files under `.github/workflows/`            | PR verify gate + release prod gate                                   |
| Runbooks      | 4 files under `docs/ops/`                     | Production deploy, release checklist, incidents, backup/restore      |

## What Needs Attention

1. **Git commit and push**: All new files need to be committed and pushed. Recommended:

   ```
   git checkout -b task/TASK-0034-production-readiness
   git add deploy/ ops/ docs/ .github/workflows/ TASKS/TASK-0034/ MEMORY/
   git commit -m "feat(ops): production packaging for Trip/Location [TASK-0034]"
   git push -u origin task/TASK-0034-production-readiness
   ```

2. **Docker integration test**: The Compose stack was NOT tested with Docker (no Docker runtime available). Before merging, run:

   ```bash
   cd deploy/compose/trip-location
   cp .env.example .env
   # Edit .env with real values
   docker compose -f docker-compose.prod.yml up -d --build
   python ../../ops/trip_location/smoke_stack.py
   ```

3. **GitHub Actions secrets**: The prod-gate workflow requires these repository secrets:
   - `POSTGRES_PASSWORD`
   - `TRIP_AUTH_JWT_SECRET`
   - `LOCATION_AUTH_JWT_SECRET`
   - `LOCATION_MAPBOX_API_KEY`
   - `LOCATION_ORS_API_KEY` (optional, if ORS validation enabled)

## Cautions

- The Compose stack uses Redpanda in dev-container mode; production Redpanda should use proper cluster mode.
- `init-db.sh` only runs on first PostgreSQL initialization; subsequent runs require manual database creation.
- Nginx config uses envsubst templating; ensure Docker image supports it (nginx:1.27-alpine does).

## Temporary / Follow-up Notes

- None. All assets are production-grade.
