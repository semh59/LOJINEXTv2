# DONE_CHECKLIST.md - TASK-0047

## Core Service Standardization

- [x] **Identity Service**: `RS256` standardized, `STRICT_AUDIENCE_CHECK` implemented.
- [x] **Trip Service**: `X-Correlation-ID` middleware verified, S2S client auth fixed.
- [x] **Location Service**: Health-check parity mode (`ignore_provider_health`) verified.
- [x] **Driver Service**: Maintenance router updated to use platform-wide audience.
- [x] **Fleet Service**: Inbound/Outbound S2S auth harmonized (removed explicit audience overrides).

## Infrastructure & Deployment

- [x] **Unified Compose**: `docker-compose.yml` consolidated for all 5 services.
- [x] **Network Isolation**: All services isolated on `backend` network; host access via Nginx only.
- [x] **Resource Hardening**: 512MB RAM limits applied to all containers.
- [x] **Log Hardening**: 10MB x 3-file rotation policy enforced.
- [x] **API Gateway**: Nginx templates updated for port 8180 consolidated routing.

## Verification & Documentation

- [x] **Data Seeding**: Refactored `seed_parity_data.sql` for V2.1 ULID schemas.
- [x] **Tracing**: Trace simulation script (`trigger_parity_trace.py`) updated for port 8180.
- [x] **Operations**: [OPERATIONS.md](./OPERATIONS.md) created for local maintenance.
- [x] **Test Plan**: [phase5_test_plan.md](../../brain/.../phase5_test_plan.md) finalized.
