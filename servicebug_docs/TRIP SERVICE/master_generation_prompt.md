# Master Generation Prompt: Trip Service Microservice (Production Hardening Edition)

**Role:** Expert Microservice Architect & Senior Backend Engineer.

**Objective:** Generate a complete, production-ready specification and implementation boilerplate for a "Trip Service" microservice that manages logistics voyages, ensuring 100% architectural integrity, scalability, and observability.

---

### Dimensions to Implement:

#### 1. Bounded Context & DDD
- Define the Trip Service as the **Aggregate Root**.
- Symmetrical boundaries: Trip depends on `Fleet` (Vehicles, Drivers) and `Location` services.
- Models: [Trip](file:///D:/PROJECT/LOJINEXT/app/schemas/sefer.py#21-27), `Itinerary`, `Stop`, `Assignment`.
- Value Objects: [TripStatus](file:///D:/PROJECT/LOJINEXT/app/schemas/sefer.py#21-27) (Planned, Assigned, In_Progress, Completed, Cancelled), `LocationPoint` (Lat/Lon), `WeightMetric`, `CostMetric`.

#### 2. API Design & Contract
- **Protocol:** Hybrid REST (External) + gRPC (Internal).
- **Standards:** OpenAPI 3.1, JSON:API or HATEOAS for state transitions.
- **Async:** Event-Driven via Transactional Outbox (CloudEvents standard).
- **Versioning:** URL-level (`/v3/trips`).
- **Patterns:** RFC 9457 Problem Details for all error responses.

#### 3. Domain Logic & Data
- Immutability for finalized trips.
- SAGA Pattern (Orchestrator) for trip booking lifecycle.
- Soft-delete logic with audit trail.
- Optimistic locking using `version` fields.

#### 4. Infrastructure & Database
- **Primary DB:** PostgreSQL with JSONB for route telemetry.
- **Cache:** Redis for rate limiting and active session management.
- **Migration:** Alembic-style versioning with data integrity guards.
- **Event Bus:** Kafka or RabbitMQ with partition keys (e.g., `vehicle_id`) to ensure Head-of-Line ordering.

#### 5. Observability & Security
- **OTEL:** OpenTelemetry traces and metrics.
- **Logging:** Structured JSON logging with `correlation_id` propagation.
- **Monitoring:** Prometheus/Grafana with SLO/SLA tracking dashboards.
- **Auth:** OAuth2/OIDC with JWT. fine-grained RBAC/ABAC (e.g., `region-based-read`).
- **Secret Management:** Integration with HashiCorp Vault.

#### 6. Language & Internationalization (i18n)
- **Technical Surface (English Priority):** All code, comments, logs, and database schemas MUST be in English.
- **Bilingual Interface:** The UI must support both Turkish (TR) and English (EN) using a resource-based i18n strategy.
- **Compliance:** Ensure no Turkish characters (except in UI resources) or mock Turkish data exists in the technical stack.

#### 7. Resilience & DevSecOps
- **Patterns:** Circuit Breaker, Bulkhead, Retry with Exponential Backoff.
- **Container:** Multi-stage Docker builds, Kubernetes HPA, PDB, and Affinity rules.
- **CI/CD:** GitOps (ArgoCD), Automated Test Pyramid (Unit -> Contract -> E2E).
- **Security:** TLS 1.3, AES-256 for PII, OWASP Top 10 hardening.

---

### Output Requirements:
1. **Architecture Overview:** Mermaid diagrams for Service boundaries and Saga flows.
2. **Schema Definition:** Pydantic V2 models and SQLAlchemy 2.0 (Async) entities.
3. **Draft Implementation:** Core repository and service layer logic with transaction guards.
4. **Environment Config:** Production-grade `docker-compose.yml` and K8s `Deployment` YAMLs.
5. **Testing Suite:** `pytest` boilerplate for unit and integration testing.

**Constraint:** Focus on "Elite" performance and "Truthful" data—no fabricated business logic or silent fallbacks. Use English only for all technical surfaces.
