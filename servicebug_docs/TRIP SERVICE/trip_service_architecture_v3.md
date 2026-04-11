# Trip Service Architecture V3: Technical Specification & Implementation Guide

## 1. Bounded Context & Strategic Design (DDD)

**Responsibility Area:** 
The Trip Service is the core orchestrator of the shipment lifecycle. It starts from the moment a logistics demand is created (either from an upstream "Booking Service" or manual entry) and ends when the trip is finalized and reconciled for payment.

**Context Symmetries:**
- **Inbound:** Receives route recommendations from `Location Service`, driver/vehicle availability from `Fleet Service`.
- **Outbound:** Emits `TripCompleted`, `TripCancelled`, `FuelAnomalyDetected` events to `Payment`, `Notification`, and `Analytics` services.

**Domain Model (Aggregate Root):**
- **Aggregate Root:** [Trip](file:///D:/PROJECT/LOJINEXT/app/schemas/sefer.py#21-27) (formerly *Sefer*)
- **Entities:** `Itinerary`, `Stop`, `Assignment`
- **Value Objects:** [TripStatus](file:///D:/PROJECT/LOJINEXT/app/schemas/sefer.py#21-27), `LocationPoint`, `WeightMetric`, `FuelEfficiency`

**Ubiquitous Language Mapping:**
- *Sefer* -> **Trip**
- *Guzergah* -> **Route/RoutePair**
- *Arac* -> **Vehicle**
- *Sofor* -> **Driver**
- *Dorse* -> **Trailer**

---

## 2. API Design & Contract

**Strategy:** Hybrid REST + gRPC
- **External/UI:** RESTful API with OpenAPI 3.1 documentation.
- **Internal Service-to-Service:** gRPC for high-performance, low-latency communication (e.g., Fleet availability checks).
- **Versioning:** URL-based (`/api/v3/trips`) with Header-based content negotiation.
- **HATEOAS:** Implementation of `links` in responses for state transitions (e.g., `cancel`, `start`, `finalize`).

**Event Schema (Async):**
- CloudEvents 1.0 compliant JSON/Protobuf schemas.
- **Transactional Outbox Pattern:** Ensures atomic persistence and event emission.

---

## 3. Domain Model & Data Management

**Persistence Strategy:**
- **CRUD with Snapshotting:** Standard SQL for state-heavy reporting.
- **State Machine:** Formal implementation of [TripStatus](file:///D:/PROJECT/LOJINEXT/app/schemas/sefer.py#21-27) transitions to prevent illegal states.
- **Transactional Consistency:** Distributed Sagas (Orchestration-based) for cross-service bookings.
- **Immutability:** Value objects (Weights, Costs) are immutable once saved; changes require a new audit-logged transaction.

---

## 4. Database Selection & Migration

**Polyglot Persistence:**
- **Primary:** PostgreSQL (Transactional Trips, Fleet associations).
- **Hot Cache:** Redis (Active Trip telemetry, Rate limiting).
- **Warehouse:** BigQuery/Cassandra (Historical logs, Telemetry archive).

**Migration & Evolution:**
- **Alembic (Backend):** Schema-first migrations with `frozen-contract` guards.
- **Zero-Downtime:** Expand-Contract pattern for breaking changes.
- **CDC:** Debezium for streaming trip updates to the analytics lake.

---

## 5. Observability & Monitoring

**Stack:**
- **Tracing:** OpenTelemetry (OTEL) with Jaeger. 100% propagation via `X-Correlation-ID`.
- **Metrics:** Prometheus exporters for RED (Rate, Error, Duration) metrics.
- **Dashboard:** Grafana with SLO/SLA tracking (e.g., "Trip Creation Latency < 200ms").
- **Logging:** Structured JSON logging to ELK/Loki.

**Health Checks:**
- Liveness: `/health/live` (process health).
- Readiness: `/health/ready` (DB/Redis/Network availability).

---

## 6. Resilience & Fault Tolerance

**Patterns (using Resilience4j or similar):**
- **Circuit Breaker:** Applied to `Weather API` and `Route API` calls.
- **Retry Policy:** Exponential backoff for transient DB deadlocks.
- **Bulkhead:** Isolation of "Predictive AI" processing from core "Trip CRUD".
- **Fallbacks:** Use cached route data if `Location Service` is down.

---

## 7. Security & Access Control

**Identity & Access:**
- **Auth:** OAuth2 + OpenID Connect (OIDC). JWT validation at Gateway (Kong/Istio).
- **RBAC/ABAC:** Fine-grained permissions (e.g., `trips:read`, `trips:write:{region}`).
- **Secrets:** HashiCorp Vault for DB credentials and API keys.
- **Data Safety:** TLS 1.3 in transit; AES-256 for PII (Driver phone numbers) at rest.

---

## 8. Scaling & Performance

**Optimization:**
- **HPA:** Scale based on CPU/Request count (Target 70% CPU).
- **Caching:** L1 (In-process memoization), L2 (Redis) for route lookups.
- **Pools:** SQLAlchemy async connection pooling (NullPool for Lambda, AsyncPool for K8s).
- **Load Testing:** Locust/K6 scripts integrated into CI/CD.

---

## 9. Containerization & Orchestration

**Deployment:**
- **Docker:** Multi-stage builds (Distroless images for production).
- **Kubernetes:** Resources (Limits/Requests), PDB (Pod Disruption Budget).
- **Service Mesh:** Istio for mTLS, traffic splitting, and retries.
- **Affinity:** `anti-affinity` rules to spread pods across AZs.

---

## 10. CI/CD & Deployment

**Workflow:**
- **GitOps:** ArgoCD for declarative state management.
- **Pipeline:** 
  - Lint/Test -> Security Scan -> Build -> Staging -> Canary (5%) -> Production.
- **Feature Flags:** Flags for "New AI Routing" or "Insurance Integration".

---

## 11. Error Handling & Logging

**Standardization:**
- **RFC 9457:** Problem Details for HTTP APIs.
- **Middleware:** Global FastAPI exception handler.
- **Audit:** Automated audit trail for all [Trip](file:///D:/PROJECT/LOJINEXT/app/schemas/sefer.py#21-27) state changes in [AdminAuditLog](file:///D:/PROJECT/LOJINEXT/app/database/models.py#654-679).

## 11. Language & Internationalization (i18n)

**Technical Surface (English-Only):**
- All code identifiers (variables, classes, functions).
- All comments, documentation, and commit messages.
- All logs and API error contracts (RFC 9457 details).
- All database schemas and event names.

**User Interface (Bilingual - TR/EN):**
- **Strategy:** Resource-based i18n using `frontend/src/resources/tr/*.ts` and `frontend/src/resources/en/*.ts`.
- **Implementation:** The UI must support dynamic language switching. All labels, notifications, and reports must be provided in both Turkish and English.
- **Exception:** Technical logs visible in admin panels may remain in English for consistency with the backend.

---

## 12. Vision Plan: LojiNext V3 "Elite Trip"

**Short-term (Q1-Q2):**
- Transition all legacy [Sefer](file:///D:/PROJECT/LOJINEXT/app/database/models.py#344-491) code to the new [Trip](file:///D:/PROJECT/LOJINEXT/app/schemas/sefer.py#21-27) domain.
- Implement 100% type safety and RFC 9457 error standards.
- Achieve 99.9% uptime for the Trip CRUD API.

**Mid-term (Q3-Q4):**
- Introduce "Predictive Routing" with real-time weather and traffic feedback loops.
- Deploy a fully-automated "Trip Anomaly Detection" system (outbox-based).
- Multi-region deployment with active-active Postgres clusters.

**Long-term (Horizon 2027):**
- Proactive "Self-Healing Trips" where the system re-routes vehicles automatically based on driver fatigue and vehicle health events.
- Zero-touch insurance integration via smart contracts.

---

## 13. Gap Analysis: Current vs. Target (V3)

| Dimension | Current Implementation ([Sefer](file:///D:/PROJECT/LOJINEXT/app/database/models.py#344-491)) | Target Architecture (`Trip Service V3`) | Status |
|-----------|---------------------------------|-----------------------------------------|--------|
| **Language** | Turkish (Sefer, Guzergah, Arac) | English-Only Backend (Trip, Route, Vehicle) | GAP |
| **Naming** | Mixed Technical Surface | English/Technical Surface Only | GAP |
| **Auth** | Database-backed Sessions (Roles) | OAuth2/OIDC + JWT + Vault Integration | GAP |
| **API** | REST (Partial OpenAPI) | Hybrid REST/gRPC + HATEOAS State Machine | GAP |
| **Tracing** | Basic Application Logs | OpenTelemetry (Jaeger) + Correlation IDs | GAP |
| **Metrics** | Admin Audit Logs | Prometheus (RED Metrics) + Grafana | GAP |
| **Resilience** | Standard Exception Handling | Circuit Breaker, Bulkhead, Saga Pattern | GAP |
| **Scaling** | Single Instance / Horizontal Pods | Multi-region Active-Active + Redis L2 Cache | GAP |
| **i18n** | Turkish resources only | Bilingual (TR/EN) Dynamic UI | GAP |

---

## 14. Implementation Guide: Step-by-Step

### Phase 1: Foundation (The Hardening)
1. **Repository Pattern:** Refactor [Sefer](file:///D:/PROJECT/LOJINEXT/app/database/models.py#344-491) repositories to use the `Aggregate Root` pattern.
2. **Schema Drift Fix:** Align all Pydantic schemas with the "Unified V2.1 Contract".
3. **Optimistic Locking:** Ensure `version` field is checked on every update to prevent race conditions.

### Phase 2: Observability & Resilience
1. **OTEL Integration:** Wrap all route handlers with OpenTelemetry traces.
2. **Circuit Breakers:** Implement `resilience4j` (or Python equivalent `circuitbreaker`) on all external API calls.
3. **Structured Logs:** Transition all `logger.info` calls to structured JSON with `context_id`.

### Phase 3: Security & Scale
1. **OAuth2 Migration:** Move away from local session hashes to a centralized OIDC provider (Okta/Keycloak).
2. **Redis Layer:** Implement write-through caching for active trips.
3. **Load Testing:** Run `k6` scripts to verify 2000 Requests/Sec capacity.

---

## 14. Verification & Hardening Checklist

- [ ] All `pytest app/tests/unit` tests are green.
- [ ] No `is_real` references in non-test code.
- [ ] API documentation (Swagger) is updated and truthfully reflects the code.
- [ ] Correlation ID is propagated to all downstream services.
- [ ] Graceful shutdown is implemented for all background workers.
