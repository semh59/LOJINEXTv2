# Trip/Location — Production Deployment Guide

## Prerequisites

- Docker Engine ≥24.0 and Docker Compose v2
- PostgreSQL client tools (`pg_dump`, `pg_restore`) for backup/restore utilities
- `.env` file configured from `.env.example` with real secrets

## Quick Start

```bash
cd deploy/compose/trip-location
cp .env.example .env
# Edit .env: set real passwords, JWT secrets, Mapbox/ORS API keys

docker compose -f docker-compose.prod.yml up -d --build
```

## Service Architecture

```
                        ┌─────────────┐
                        │   Nginx     │ :80
                        └──────┬──────┘
                   ┌───────────┼───────────┐
                   ▼                       ▼
            ┌─────────────┐        ┌──────────────┐
            │  trip-api    │ :8101  │ location-api │ :8103
            └─────────────┘        └──────────────┘
                   │                       │
     ┌─────────────┼─────────┐            │
     ▼             ▼         ▼            ▼
┌──────────┐ ┌─────────┐ ┌────────┐ ┌──────────────┐
│enrichment│ │ outbox   │ │cleanup │ │  processing  │
│ worker   │ │ relay    │ │ worker │ │  worker      │
└──────────┘ └─────────┘ └────────┘ └──────────────┘
                   │
                   ▼
            ┌─────────────┐
            │  Redpanda   │ :9092 (internal), :19092 (external)
            └─────────────┘

            ┌─────────────┐
            │ PostgreSQL  │ :5432
            └─────────────┘

            ┌─────────────┐     ┌──────────┐
            │ Prometheus  │ :9090│ Grafana  │ :3000
            └─────────────┘     └──────────┘
```

## Database Setup

The `init-db.sh` script automatically creates both databases on first PostgreSQL start:

- `trip_service` (default POSTGRES_DB)
- `location_service`

### Running Migrations

```bash
# Trip Service
docker compose -f docker-compose.prod.yml exec trip-api alembic upgrade head

# Location Service
docker compose -f docker-compose.prod.yml exec location-api alembic upgrade head
```

## Environment Variables

See `.env.example` for the complete list. Key variables:

| Variable                   | Service  | Required    | Description                        |
| -------------------------- | -------- | ----------- | ---------------------------------- |
| `POSTGRES_PASSWORD`        | Infra    | Yes         | Database password                  |
| `TRIP_AUTH_JWT_SECRET`     | Trip     | Yes         | JWT signing secret (≥32 bytes)     |
| `TRIP_BROKER_TYPE`         | Trip     | Yes (prod)  | Must be `kafka` in prod            |
| `LOCATION_AUTH_JWT_SECRET` | Location | Yes         | JWT signing secret (≥32 bytes)     |
| `LOCATION_MAPBOX_API_KEY`  | Location | Yes         | Mapbox Directions API key          |
| `LOCATION_ORS_API_KEY`     | Location | Conditional | Required if ORS validation enabled |

## Health Checks

```bash
# Liveness
curl http://localhost:8101/health   # Trip
curl http://localhost:8103/health   # Location

# Readiness (includes dependency + worker checks)
curl http://localhost:8101/ready    # Trip
curl http://localhost:8103/ready    # Location

# Metrics (Prometheus format)
curl http://localhost:8101/metrics  # Trip
curl http://localhost:8103/metrics  # Location
```

## Monitoring

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin by default)
- Pre-provisioned dashboard: "Trip/Location — Production Overview"

## Scaling Workers

Workers are separate containers and can be scaled independently:

```bash
docker compose -f docker-compose.prod.yml up -d --scale trip-enrichment=3
docker compose -f docker-compose.prod.yml up -d --scale location-processing=2
```

## Stopping / Restarting

```bash
# Graceful stop (keeps volumes)
docker compose -f docker-compose.prod.yml stop

# Full teardown (removes volumes)
docker compose -f docker-compose.prod.yml down -v
```
