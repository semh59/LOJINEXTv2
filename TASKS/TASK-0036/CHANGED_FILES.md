# CHANGED_FILES.md

## Phase D: Vehicle Spec Versions

- `src/fleet_service/repositories/vehicle_spec_repo.py`
- `src/fleet_service/services/vehicle_spec_service.py`
- `src/fleet_service/routers/vehicle_spec_router.py`

## Phase E: Trailer Mirror

- `src/fleet_service/repositories/trailer_repo.py`
- `src/fleet_service/repositories/trailer_spec_repo.py`
- `src/fleet_service/services/trailer_service.py`
- `src/fleet_service/routers/trailer_router.py`

## Phase F: Internal Service APIs

- `src/fleet_service/clients/driver_client.py`
- `src/fleet_service/clients/trip_client.py`
- `src/fleet_service/services/internal_service.py`
- `src/fleet_service/routers/internal_router.py`

## Phase G: Outbox Worker & Readiness

- `src/fleet_service/broker.py`
- `src/fleet_service/workers/outbox_relay.py`
- `src/fleet_service/worker_heartbeats.py`
- `src/fleet_service/entrypoints/worker.py` (modify)
- `src/fleet_service/routers/health.py` (modify)
