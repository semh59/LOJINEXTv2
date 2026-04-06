# CHANGED_FILES.md - TASK-0047

## Infrastructure & Orchestration

- [MODIFY] [docker-compose.yml](../../deploy/compose/production-parity/docker-compose.yml) — Resource limits, logging, and port lockdown.
- [MODIFY] [.env.example](../../deploy/compose/production-parity/.env.example) — Added `IDENTITY_AUTH_STRICT_AUDIENCE_CHECK`.
- [MODIFY] [nginx.conf.template](../../deploy/compose/production-parity/nginx/nginx.conf.template) — Consolidated upstreams.

## Database & Data Parity

- [MODIFY] [seed_parity_data.sql](../../deploy/compose/production-parity/seed_parity_data.sql) — Refactored for V2.1 ULID schemas and property names.

## Service Remediation (Audience Claim Harmonization)

- [MODIFY] [token_service.py](../../services/identity-service/src/identity_service/token_service.py) — Strict audience check implementation.
- [MODIFY] [dependencies.py](../../services/trip-service/src/trip_service/dependencies.py) — S2S audience alignment.
- [MODIFY] [driver_client.py](../../services/fleet-service/src/fleet_service/clients/driver_client.py) — Removed specific audience overrides.
- [MODIFY] [trip_client.py](../../services/fleet-service/src/fleet_service/clients/trip_client.py) — Removed specific audience overrides.
- [MODIFY] [maintenance.py](../../services/driver-service/src/driver_service/routers/maintenance.py) — Removed specific audience overrides.

## Documentation

- [NEW] [OPERATIONS.md](../../deploy/compose/production-parity/OPERATIONS.md) — Operational handover manual.
