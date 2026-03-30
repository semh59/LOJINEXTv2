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

superseded by [2026-03-28, Trip Service outbox relay avoids duplicate publishes]

---

## [2026-03-28] Trip Service outbox relay avoids duplicate publishes

### Context

At-least-once outbox delivery caused a duplicate-publish window when broker publish succeeded but the relay DB commit failed. The requirement is to prevent duplicates in Trip Service even if that introduces a different tradeoff.

### Decision

The outbox relay now uses a `PUBLISHING` state and only publishes `READY/FAILED` rows. Rows are marked `PUBLISHING` before any broker publish. After publish, rows are marked `PUBLISHED`. The relay does not republish rows already in `PUBLISHING`.

### Alternatives Considered

- Kafka transactions: rejected for operational complexity in this phase.
- Accept at-least-once: rejected due to “no accepted risks” requirement.

### Consequences

- Duplicate publishes are avoided by design.
- A failed commit after publish can leave a row in `PUBLISHING` requiring manual intervention.
- Operational runbooks must include handling for stuck `PUBLISHING` rows.

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

---

## [2026-03-28] Trip Service outbox duplicate-publish window is accepted (at-least-once)

### Context

Outbox relay publishes events to the broker and then commits the database transaction. If the broker publish succeeds but the DB commit fails, the row can be retried and published again. This is a standard at-least-once failure window.

### Decision

We accept the duplicate-publish window as an at-least-once delivery tradeoff. Downstream consumers must de-duplicate by `event_id`. No code mitigation will be added in this phase.

### Alternatives Considered

- Broker transactions or two-phase commit: rejected due to complexity and operational coupling.
- Additional publish markers/locks in DB: rejected for now; may be revisited if consumers cannot de-duplicate reliably.

### Consequences

- Event delivery is at-least-once; consumers must handle duplicates.
- Documentation must state this explicitly for downstream teams.

### Status

superseded by [2026-03-30, Trip outbox remediation uses per-event commits with stale-claim recovery]
---

## [2026-03-28] Location Service no longer owns import/export responsibilities

### Context

Trip Service already models Excel ingest/export as a separate service-to-service contract.
Location Service still exposes its own import/export endpoints, schema objects, and runtime dependencies even though that responsibility is being split out.

### Decision

- Location Service no longer owns file-based or spreadsheet-based import/export responsibilities.
- The public `POST /v1/import` and `GET /v1/export` endpoints are removed.
- Import/export-specific tables, config, errors, metrics, and runtime dependencies are removed from Location Service.
- The only downstream contracts Location Service must preserve for Trip Service are route resolve and trip-context.

### Alternatives Considered

- Leave the endpoints in place but return `410 Gone`: rejected because it preserves dead contract surface and schema baggage.
- Keep the schema/models but remove only routers: rejected because it leaves ambiguous ownership and unused runtime complexity.

### Consequences

- Location Service becomes a narrower route-authority service.
- Any future Excel/import-export behavior must live in a separate service, not be reintroduced into Location Service.
- Trip Service contracts remain unchanged and continue consuming only internal resolve/trip-context endpoints.

### Status

active

---

## [2026-03-28] Location and Trip services share a JWT signing domain for service auth

### Context

TASK-0019 hardens `location-service` with bearer-token auth while `trip-service` already signs JWTs for its own public and internal callers.
Trip Service must call Location internal endpoints as a service, and the smoke stack needs one deterministic auth model for both services.

### Decision

- `location-service` validates bearer JWTs using its own env surface: `LOCATION_AUTH_JWT_SECRET` and `LOCATION_AUTH_JWT_ALGORITHM`.
- `trip-service` signs outbound Location service tokens with the same signing domain and sends `role=SERVICE` and `service=trip-service`.
- Public Location endpoints require `ADMIN` or `SUPER_ADMIN`; internal `/internal/v1/*` endpoints currently accept only the `trip-service` service claim.

### Alternatives Considered

- Separate token issuers and key domains for Location immediately: rejected for this phase because it adds operational and integration complexity before the release blockers are closed.
- Leave Location unauthenticated and rely on network isolation: rejected because it leaves a real prod security gap.

### Consequences

- Deployments must keep Trip and Location JWT signing settings aligned.
- Any future internal caller of Location must either use the same signing domain or trigger a new auth design decision.
- Smoke and integration tests now exercise the same service-auth model as production.

### Status

active

---

## [2026-03-28] Location hardening work is split by severity

### Context

The first hardening plan mixed release blockers with deeper cleanup and architecture work. That made it harder to distinguish what must ship now from what should be cleaned next.

### Decision

- `TASK-0019` owns only the P0/P1 work: auth, readiness, live provider/runtime fixes, approval/ETag contract completion, Trip/Location error mapping, and smoke verification.
- `TASK-0020` owns the deferred P2 work: dead surface cleanup, persistent worker redesign, deeper observability cleanup, and remaining spec-completeness work.

### Alternatives Considered

- Ship one large hardening tranche: rejected because it mixes blockers with cleanup and increases delivery risk.
- Ignore the cleanup entirely: rejected because the deferred work still matters and must remain explicitly tracked.

### Consequences

- Release blockers can be reviewed and shipped without waiting on the larger cleanup tranche.
- The remaining Location technical debt is not silent; it stays visible in `TASKS/TASK-0020/`.
- Reviews can judge TASK-0019 on production correctness instead of on cleanup scope.

### Status

active

---

## [2026-03-29] Location frontend contract work stays separate from cleanup

### Context

After TASK-0019, `location-service` was production-hardened but still backend-shaped for a future admin/Tauri frontend. At the same time, TASK-0020 already existed to track P2 cleanup and architecture hardening.

### Decision

- Frontend-facing public contract work for `location-service` is tracked as its own task (`TASK-0021`), not folded into TASK-0020.
- TASK-0021 is allowed to change only the public `/v1/*` contract surface, request/response schemas, and related tests.
- TASK-0020 remains responsible for cleanup, dead-surface removal, and worker/architecture hardening.

### Alternatives Considered

- Fold frontend-contract work into TASK-0020: rejected because it mixes product-contract work with cleanup and makes review scope ambiguous.
- Treat frontend contract as implicit documentation only: rejected because the contract needs executable tests and explicit API decisions.

### Consequences

- Location public contract changes can be reviewed independently from cleanup work.
- Future frontend work has a stable backend contract before TASK-0020 lands.
- Cleanup work must not silently change frontend-visible behavior without a new explicit decision.

### Status

active

---

## [2026-03-29] Location public profile codes are locked to TIR and VAN

### Context

The frontend contract needs a closed, testable `profile_code` surface. `location-service` previously treated `profile_code` as a free-form string in public schemas.

### Decision

- Public `location-service` request and response schemas now lock `profile_code` to the closed enum values `TIR` and `VAN`.
- `TIR` remains the default.
- Unsupported public `profile_code` values are rejected through the generic validation contract.

### Alternatives Considered

- Keep `profile_code` as an unrestricted string: rejected because it leaves frontend options ambiguous and untestable.
- Move the enum decision to cleanup work later: rejected because the frontend contract needs the decision now.

### Consequences

- Future frontend clients can render a closed selection set for profile choice.
- Any new public profile code will require an explicit schema and contract update.
- Internal Location data storage remains unchanged; only the public contract is tightened here.

### Status

active


## [2026-03-30] TASK-0033 stays separate from TASK-0020

### Context

The requested audit remediation spans Trip Service public/admin behavior, Trip worker reliability, and Location Service correctness gaps. `TASKS/TASK-0020` already exists for deferred Location cleanup and explicitly excludes Trip API changes.

### Decision

`TASK-0033` owns the current-HEAD audit remediation across Trip and Location services. `TASK-0020` remains the separate deferred architecture/cleanup task and is not expanded to absorb this work.

### Alternatives Considered

- Fold the work into `TASK-0020`: rejected because it would blur scope, re-open a deferred task, and mix Trip API changes into a Location-only cleanup track.
- Leave the work undocumented and patch directly: rejected because it would hide the remediation scope from future agents.

### Consequences

- TASK tracking now reflects a dedicated cross-service remediation task.
- Future agents should keep TASK-0033 and TASK-0020 concerns separate.

### Status

active

---

## [2026-03-30] Trip outbox remediation uses per-event commits with stale-claim recovery

### Context

Current HEAD still has a duplicate-publish blast radius when multiple outbox rows are claimed in one transaction and their final states are committed together. The ORM model also drifted from the schema by omitting `TripOutbox.last_error_code`.

### Decision

- `TripOutbox` keeps explicit `PUBLISHING` claim metadata plus a mapped `last_error_code` column.
- The relay claims a batch once, then reloads and commits each published row independently.
- Stale `PUBLISHING` rows remain recoverable through claim expiry.
- Delivery remains at-least-once; downstream consumers must still de-duplicate by `event_id`.

### Alternatives Considered

- Keep a single end-of-batch commit: rejected because one failed row or process crash broadens the duplicate/replay window for the whole batch.
- Move to broker transactions: rejected because that is larger infrastructure work than this remediation task.

### Consequences

- Successful publishes are durably recorded one row at a time.
- Crash recovery remains automatic through expired claims instead of manual stuck-row cleanup only.
- Worker tests must cover mixed-success batches and persisted `last_error_code`.

### Status

active

---

## [2026-03-30] Audit remediation defaults hide tombstones, cache provider probes, and use hybrid concurrency

### Context

TASK-0033 had to lock several behavioral defaults before implementation: how list endpoints treat soft-deleted rows, how readiness probes external providers, and how to close race conditions in Trip and Location services.

### Decision

- Admin list endpoints hide soft-deleted rows by default unless explicitly filtered for them.
- Location readiness uses cached live provider probes with a short TTL rather than config-only checks or uncached probes on every request.
- Trip overlap protection uses advisory transaction locks; Location live-pair races use a DB unique index plus friendly prechecks.

### Alternatives Considered

- Include tombstones by default: rejected because it leaks deleted records into normal admin views.
- Config-only readiness: rejected because it cannot detect dead or unauthorized upstream providers.
- App-only or DB-only concurrency strategy everywhere: rejected because Trip overlap is a better fit for advisory locks while pair uniqueness is a better fit for a DB uniqueness guard.

### Consequences

- Clients must explicitly request tombstones.
- `/ready` gains cached live-provider status and can return 503 for real provider outages.
- Concurrency behavior becomes more deterministic without taking on a heavier Trip exclusion-constraint design.

### Status

active

---

## [2026-03-30] TASK-0034 locks full production packaging for Trip and Location

### Context

After TASK-0033, both services were materially closer to production correctness, but they still ran with development-shaped topology and ad hoc operational tooling. The user explicitly asked for full production readiness rather than another incremental cleanup pass.

### Decision

- `TASK-0034` owns the release packaging layer for `trip-service` and `location-service`.
- Production packaging includes split API/worker processes, full-stack Docker Compose assets, bundled Nginx + Prometheus + Grafana, internal unauthenticated `/metrics`, repo-owned smoke/soak/backup/restore tooling, and dedicated GitHub Actions verify/prod-gate workflows.
- Location processing must move from API-managed in-process tasks to a durable claimed worker loop.
- The prod-gate workflow must require live provider proof and fail when mandatory secrets are absent.

### Alternatives Considered

- Stop at code correctness and rely on manual ops setup: rejected because it leaves the system short of the requested prod-ready bar.
- Fold this work into TASK-0033 or TASK-0020: rejected because it mixes correctness remediation with packaging/ops scope and obscures review boundaries.
- Keep `/metrics` authenticated or public by default: rejected because internal unauthenticated metrics behind reverse-proxy/network isolation is the chosen operational model.

### Consequences

- Production readiness is now judged on packaged deployment and verification assets, not only service code.
- Compose, workflow, and runbook changes are first-class deliverables of this task.
- API lifecycles must remain narrow; long-running workers are separate processes going forward.

### Status

active
