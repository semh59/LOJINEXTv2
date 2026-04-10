# SERVICE_REGISTRY.md — Service Registry

**This file is the single source of truth for all service identities.**
PLATFORM_STANDARD.md references this file. No service name is hardcoded in the standard.

Last updated: 2026-04-11
Version: 1.0.1

---

## Registered Services

When adding a new service, follow the onboarding procedure in PLATFORM_STANDARD.md §19.
Every column must be filled. No orphan entries.

| Service           | Module            | Port | Database           | Domain Owner                    | Status   |
|-------------------|-------------------|------|--------------------|---------------------------------|----------|
| identity-service  | identity_service  | 8105 | identity_service   | Authentication, users, JWT keys | active   |
| trip-service      | trip_service      | 8101 | trip_service       | Trip lifecycle                  | active   |
| location-service  | location_service  | 8103 | location_service   | Routes, location authority      | active   |
| driver-service    | driver_service    | 8104 | driver_service     | Driver master data              | active   |
| fleet-service     | fleet_service     | 8102 | fleet_service      | Vehicles, trailers              | active   |
| telegram-service  | telegram_service  | 8106 | telegram_service   | Telegram bot integration        | active   |

## Locked Service Call Boundaries

These call paths are locked by ADR. Changes require a new ADR in `docs/adr/`.

| From  | To        | Endpoint                                        | ADR    |
|-------|-----------|-------------------------------------------------|--------|
| trip  | location  | POST /internal/v1/routes/resolve                | ADR-001|
| trip  | fleet     | POST /internal/v1/trip-references/validate      | ADR-001|
| fleet | driver    | POST /internal/v1/drivers/eligibility/check     | ADR-001|
| driver| trip      | GET /internal/v1/trips/driver-check/{driver_id} | ADR-001|
| telegram | trip   | internal trip ingestion endpoints                | —      |
| telegram | driver | internal driver query endpoints                  | —      |
| telegram | fleet  | internal vehicle/trailer lookup by plate         | —      |

## Shared Packages

| Package         | Location                    | Purpose                          |
|-----------------|-----------------------------|----------------------------------|
| platform-auth   | packages/platform-auth      | JWT verification, service tokens |
| platform-common | packages/platform-common    | Shared utilities                 |

## Kafka Topics

| Topic                 | Producer         | Event Examples                          |
|-----------------------|------------------|-----------------------------------------|
| trip.events.v1        | trip-service     | trip.created, trip.status_changed       |
| fleet.events.v1       | fleet-service    | fleet.vehicle_assigned                  |
| location.events.v1    | location-service | location.route_updated                  |
| driver.events.v1      | driver-service   | driver.created, driver.telegram_changed |
| identity.events.v1    | identity-service | identity.user_created, identity.user_deactivated |

## Infrastructure

| Component   | Image/Version           | Purpose              |
|-------------|-------------------------|----------------------|
| PostgreSQL  | postgres:16-alpine      | All service databases|
| Kafka       | redpanda:v24.1.7        | Event streaming      |
| Nginx       | nginx:1.27-alpine       | Reverse proxy        |
| Prometheus  | prom/prometheus:v2.53.0 | Metrics collection   |
| Grafana     | grafana/grafana-oss:11.1.0 | Dashboards        |
| Redis       | redis:7                 | Rate limiting, cache |

---

## Port Allocation

Ports 8101-8199 are reserved for platform services.
External-facing ports (19092, 3000, 5432, 9090) are for development tooling only.

| Port | Assigned To       | Purpose        |
|------|-------------------|----------------|
| 8101 | trip-service      | API            |
| 8102 | fleet-service     | API            |
| 8103 | location-service  | API            |
| 8104 | driver-service    | API            |
| 8105 | identity-service  | API            |
| 8106 | telegram-service  | API            |
| 8107 | (available)       | —              |
| 8108 | (available)       | —              |

---

## Governance

- Adding a service: follow §19 in PLATFORM_STANDARD.md, then add a row here.
- Removing a service: mark `Status: deprecated`, do not delete the row.
- Changing a port or database: requires a DECISIONS.md entry first.
- This file MUST stay in sync with `deploy/compose/` and `MANIFEST.yaml`.
