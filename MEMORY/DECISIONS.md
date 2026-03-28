# DECISIONS.md

# Decisions Log

Every significant decision is recorded here:
architecture, technology, direction changes, rejected alternatives.

An agent that does not know a decision was made will make it again — possibly differently.
An agent that does not know why a decision was made may undo it for reasonable-sounding reasons.

---

## How to Write a Decision

```
## [YYYY-MM-DD] Short title

### Context
What situation prompted this decision?

### Decision
What was decided? Be specific.

### Alternatives Considered
What else was evaluated and why was it rejected?

### Consequences
What does this change or constrain going forward?

### Status
active | superseded by [date, title] | reversed on [date]
```

Decisions are never deleted.
If reversed: mark the old one superseded, write a new entry explaining the change.

---

## [YYYY-MM-DD] Agent memory lives in repository files, not in conversation

### Context

Agent sessions have token limits. Conversation context is lost when a session ends.
Agents working on the same project accumulate invisible divergence — each carrying
different mental models built only from their own session history.

### Decision

All project memory lives in files inside the repository.
No agent relies on conversation context as the source of truth.

### Alternatives Considered

- External tools (Notion, Docs): not colocated with code, not visible to automated agents
- System prompt summaries: stale immediately, no reliable update mechanism

### Consequences

Every session starts with a file-reading phase.
In exchange: context loss is eliminated. Any agent can continue any task.

### Status

active

---

## [YYYY-MM-DD] Plan before code is mandatory

### Context

Agents that start coding immediately change scope mid-task, touch wrong files,
or build the wrong thing. A misunderstanding in code costs 10× more to fix than
a misunderstanding in a plan.

### Decision

No code is written until PLAN.md exists and is complete.

### Alternatives Considered

- Plan only for large tasks: rejected — "large" is consistently misjudged
- Skip for quick fixes: rejected — the same failure modes occur at any size

### Consequences

Every task requires a planning step. Scope creep is dramatically reduced.

### Status

active

---

## [2026-03-23] Trip Service technology stack: Python + FastAPI + SQLAlchemy + PostgreSQL

### Context

Trip Service V8 spec is language-agnostic. A technology stack is needed for greenfield implementation.
The spec heavily implies PostgreSQL via `SELECT ... FOR UPDATE SKIP LOCKED`, `TIMESTAMPTZ`, partial unique indexes.

### Decision

- **Runtime:** Python 3.12+
- **Framework:** FastAPI (async ASGI)
- **ORM:** SQLAlchemy 2.0 (async) with Alembic for migrations
- **Database:** PostgreSQL 15+
- **ID generation:** ULID (via `python-ulid`)
- **Async:** `asyncpg` driver
- **Testing:** pytest + httpx.AsyncClient
- **Object storage:** Local filesystem for dev, abstract interface for S3-compatible prod
- **Project location:** `services/trip-service/` within the LOJINEXTv2 repository

### Alternatives Considered

- Go: Higher raw concurrency performance, but slower greenfield development velocity. Spec is compatible.
- Node.js + NestJS: Good if aligning with frontend, but Python is more common for backend-heavy services with complex business logic.
- SQLite: Rejected — spec requires PostgreSQL features (SKIP LOCKED, partial unique indexes, TIMESTAMPTZ)

### Consequences

- All service code lives in `services/trip-service/`
- Python virtual environment management required
- PostgreSQL must be available for development and testing
- Alembic manages schema migrations

### Status

active

---

## [2026-03-27] Trip Service broker transport is Kafka in prod with environment-specific fallbacks

### Context

Trip Service already relied on an abstract outbox broker, but production transport was still a log-only stub.
The user explicitly locked Kafka as the real transport while also requiring test and local-development fallbacks.

### Decision

- Trip Service publishes outbox events to Kafka via `confluent-kafka` async producer.
- The default broker resolution is environment-specific:
  - `prod` -> `kafka`
  - `test` -> `noop`
  - `dev` -> `log`
- The event topic remains a single JSON topic: `trip.events.v1`.
- No schema registry is introduced in V1.

### Alternatives Considered

- Keep the log broker only: rejected because it does not satisfy production delivery.
- Hardcode Kafka in every environment: rejected because tests and local development need deterministic non-network fallbacks.
- Add schema registry immediately: rejected because the locked rollout kept V1 payloads as JSON outbox bodies.

### Consequences

- Trip Service now has an expanded broker environment surface.
- Production readiness must include broker connectivity, not only database liveness.
- Container packaging must include the Kafka client dependency.

### Status

active

---

## [2026-03-27] Trip Service readiness hard-gates downstream dependencies and uses internal route resolve

### Context

Trip Service approval, enrichment, and reference validation depend on downstream services, but readiness previously reported soft or fake checks.
Trip enrichment was already calling an internal location resolve endpoint that did not exist.

### Decision

- `/ready` is a hard dependency gate for:
  - database
  - broker connectivity
  - Location Service `POST /internal/v1/routes/resolve`
  - Fleet Service `POST /internal/v1/trip-references/validate`
  - enrichment worker heartbeat
  - outbox relay heartbeat
- Location Service now owns an internal exact-match route resolve endpoint returning `{route_id, pair_id, resolution}` for active forward/reverse pointers.
- Trip Service validates fleet references on write and treats fleet unavailability as a `503` dependency failure.

### Alternatives Considered

- Keep degraded downstream checks in readiness: rejected because the user locked "all deps hard".
- Resolve routes inside Trip Service: rejected because route authority belongs to Location Service.
- Delay fleet validation to async processing: rejected because the user locked validate-on-write semantics.

### Consequences

- Trip Service startup and readiness are now meaningfully coupled to downstream contracts.
- Tests need explicit stubs for downstream probes and validation.
- Location Service became part of the trip-service production contract surface.

### Status

active

---

## [2026-03-27] Trip Service product contract is bearer-token, route-pair driven, and service-ingest based

### Context

TASK-0011 replaced the old V8-centered trip contract with the locked product rules required before a future Tauri desktop client can rely on the backend.
The old contract still assumed header-based actor identity, raw `route_id` input, and no explicit structured Excel/Telegram producer boundary.

### Decision

- Public trip-service endpoints use `Authorization: Bearer` JWT auth with `ADMIN` and `SUPER_ADMIN` roles.
- Internal Telegram and Excel APIs use service bearer tokens with `role=SERVICE`.
- Manual create uses `route_pair_id` and location-service trip-context, not raw `route_id`.
- Empty return remains a separate action and derives the reverse leg from the base trip's `route_pair_id`, using the `-B` suffix.
- Trip aggregates persist origin/destination snapshots, planned duration, planned end, review reason, and source reference keys.
- Telegram full ingest, Telegram fallback ingest, Excel ingest, and Excel export-feed are structured service contracts; trip-service does not own files or PDFs.
- Hard delete is a `SUPER_ADMIN`-only reasoned action and writes an immutable full-snapshot audit row before deletion.

### Alternatives Considered

- Keep `X-Actor-*` headers in prod: rejected because the locked contract moved to bearer-token auth.
- Keep raw `route_id` on create: rejected because the user locked location-driven create via single pair selection.
- Reintroduce file-based Excel endpoints: rejected because Excel ownership moved to a separate service.

### Consequences

- Tauri desktop work must use bearer tokens, ETag/If-Match, and route-pair lookups against the new contract.
- Downstream Telegram and Excel services must integrate with the structured internal ingest/export APIs instead of file/job endpoints.
- Location-service trip-context is now part of the production dependency surface for trip creation, reverse derivation, and overlap windows.

### Status

active
