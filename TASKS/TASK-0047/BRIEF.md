# BRIEF.md

## Task ID

TASK-0047

## Task Name

Phase 3: Deep System Integration and Production Parity

## Phase

Phase 3 - Deep Integration

## Primary Purpose

Standardize the entire 5-service microservice stack on common observability, authentication, and deployment patterns, ensuring 100% architectural parity and end-to-end integration readiness.

## Expected Outcome

- All 5 services (`Identity`, `Trip`, `Location`, `Fleet`, `Driver`) run in a unified `docker-compose` environment with shared PostgreSQL and Redpanda.
- End-to-end RS256/JWKS authentication is verified across service-to-service boundaries without mocks in the integration environment.
- Distributed tracing (`X-Correlation-ID`) and Prometheus metrics are standardized across all service entrypoints.
- Production-grade deployment manifests (Compose, Nginx, Prometheus/Grafana) are finalized and validated.

## In Scope

- Creation of a Master Production-Parity Compose file.
- Standardization of Prometheus `/metrics` endpoints across all services.
- Verification of `X-Correlation-ID` middleware across all API and Worker boundaries.
- End-to-end "Happy Path" verification (Trip Lifecycle) in the unified environment.
- Removal of any remaining environment-specific divergence in `env.py` or `config.py`.

## Out of Scope

- Major business logic changes.
- Performance tuning beyond baseline stability.
- Kubernetes-specific orchestration.

## Dependencies

- Completed Phase 2 Hardening (PostgreSQL, RS256 Baseline).
- Existing Docker Compose templates in `deploy/`.
