# PLAN.md - TASK-0047

## Goal

Achieve 100% production parity for the 5-service core stack through unified orchestration and standardized observability.

---

## Phase A: Infrastructure Consolidation (Unified Orchestration)

1. **Consolidate shared resources**:
   - Move from service-local internal DBs/Brokers to a single `docker-compose.yml` for all 5 services.
   - Use a shared PostgreSQL instance (separate databases per service).
   - Use a shared Redpanda cluster.
2. **Standardize Health/Readiness**:
   - All 5 services must use `/ready` and `/health` with truthful dependency probes.
   - Update `deploy/compose/production-parity.yml` with healthchecks that block service startup until dependencies are reachable.

## Phase B: Observability & Standardization (The "Deep" Part)

1. **Metrics Standardization**:
   - Implement common Prometheus labels (`service`, `env`, `version`).
   - Standardize error histograms across all API routers.
2. **Tracing & Correlation**:
   - Verify `X-Correlation-ID` middleware is active in all services.
   - Ensure all outbound `httpx` calls and `kafka` produce calls include the correlation header.
3. **Log Contextualization**:
   - Ensure all logs (API and Worker) include `correlation_id` in Structured JSON format.

## Phase C: High-Fidelity System Verification (No Mocks)

1. **End-to-End Auth Chain**:
   - Verify `Trip -> Fleet -> Driver` token propagation without mocking `ServiceTokenCache`.
2. **Outbox Relay Stress Test**:
   - Verify that events produced by `Trip` are successfully processed by `Fleet` and `Driver` in a multi-container environment.
3. **Identity JWKS Rotation**:
   - Verify that services reload JWKS automatically when `Identity-Service` rotates keys.

## Phase D: Finalization

1. Update all `README.md` files to reflect the unified `production-parity.yml` startup.
2. Produce the Phase 3 Readiness Report.
