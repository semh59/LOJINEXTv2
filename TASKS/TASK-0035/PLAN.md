# PLAN.md

## Goal
Implement Phase 1 of the production audit remediation: truthfully readiness, heartbeat persistence, and Fleet validation ADR.

## Proposed Changes

### 1. ADR-001: Fleet Validation Architecture
- Create docs/adr/001-fleet-validation-architecture.md.
- Document Option 1 (aggregation facade) and justification.
- Update MEMORY/DECISIONS.md to reference ADR-001.

### 2. DB-Backed Heartbeats (Trip & Location)
- **Trip Service**:
  - Add WorkerHeartbeat model to models.py.
  - Create Alembic migration for worker_heartbeats table.
  - Update src/trip_service/worker_heartbeats.py to use SQLAlchemy.
- **Location Service**:
  - Add WorkerHeartbeat model.
  - Create Alembic migration.
  - Update src/location_service/worker_heartbeats.py.

### 3. Readiness Probes Enforcement
- Update health.py in both services to use get_worker_heartbeat_snapshot.
- Include dependency probes (Fleet, Location) in Trip readiness.
- Update docker-compose.prod.yml and docker-compose.ci.yml health checks to use /ready.
- Update GitHub Actions workflows (	rip-location-verify.yml).

## File List
- docs/adr/001-fleet-validation-architecture.md [NEW]
- MEMORY/DECISIONS.md [MODIFY]
- services/trip-service/src/trip_service/models.py [MODIFY]
- services/trip-service/src/trip_service/worker_heartbeats.py [MODIFY]
- services/trip-service/alembic/versions/c3d4e5f6a1b2_add_worker_heartbeats.py [NEW]
- services/trip-service/src/trip_service/routers/health.py [MODIFY]
- services/location-service/src/location_service/models.py [MODIFY]
- services/location-service/src/location_service/worker_heartbeats.py [MODIFY]
- services/location-service/alembic/versions/d4e5f6a1b2c3_add_worker_heartbeats.py [NEW]
- services/location-service/src/location_service/routers/health.py [MODIFY]
- docker-compose.prod.yml [MODIFY]
- docker-compose.ci.yml [MODIFY]
- .github/workflows/trip-location-verify.yml [MODIFY]

## Verification Plan
### Automated
- pytest services/trip-service/tests
- pytest services/location-service/tests
- Verify migrations: uv run alembic upgrade head (in both service folders)
### Manual
- docker compose -f docker-compose.prod.yml up -d
- curl http://localhost:8080/health/ready (expect 200 after boot, 503 if a worker is killed)
- Verify docs/adr/001-fleet-validation-architecture.md existence.
