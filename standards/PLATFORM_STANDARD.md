# PLATFORM_STANDARD.md
# Platform Engineering Standard

**This file is binding.** No agent — human or AI — touches any service without reading it first.
This file supersedes any per-service pattern that contradicts it.
"It was done this way before" is not a justification for a non-standard pattern.

Service identities, ports, and call boundaries live in `standards/SERVICE_REGISTRY.md`.
This file MUST NOT hardcode service names in rules, examples, or checklists.

> **Note on examples:** Code examples in this file use concrete service names
> (e.g., `trip`, `fleet`, `driver`) for readability. These are illustrative only
> and refer to services registered in `standards/SERVICE_REGISTRY.md`.
> Rules themselves are generic and apply to all current and future services.

Last updated: 2026-04-11
Version: 3.0.1

---

## GOVERNANCE

### Who owns this file
This file is owned by the project. Any change requires a `standards/DECISIONS.md`
entry with: date, reason, and the section number changed. No undated changes.

### How to update
1. Write the decision in `standards/DECISIONS.md` first.
2. Update this file.
3. Update `standards/KNOWN_ISSUES.md` if the change reveals existing drift.
4. On the next repair task for each affected service, the agent applies the change.

### What "binding" means
- A pattern that contradicts this standard is a defect, not a style choice.
- An agent that defers to "how it was done before" instead of this file is wrong.
- This standard is agent-agnostic. It does not reference any specific AI tool, editor, or workflow.

### Versioning
- **Patch** (3.0.x): Clarifications, typo fixes, added examples. No rule changes.
- **Minor** (3.x.0): New rules that do not break existing compliant code.
- **Major** (x.0.0): Changes that require code modification in existing services.
- Version is updated on every change. Date and version are always in the header.

### Approval
- Patch changes: any agent or developer may apply.
- Minor changes: require a DECISIONS.md entry.
- Major changes: require a DECISIONS.md entry and explicit project owner approval.

### Agent integration
Agents (AI coding tools) read this file at session start. Each agent may have its own
instruction file (CLAUDE.md, .cursorrules, etc.) but those files are thin wrappers that
point here. Standards live in `standards/`, not in agent-specific config.

---

## TABLE OF CONTENTS

1.  Domain Boundaries and Service Isolation
2.  Technology Stack
3.  Required File Structure
4.  Authentication
5.  Role Standard
6.  Error Response Format
7.  API Design and Versioning
8.  Pagination
9.  Outbox Model
10. Health, Ready, and Metrics Endpoints
11. Middleware
12. Logging
13. Observability — Prometheus Metrics
14. Database and Migrations
15. Message Broker
16. ID and Timestamp Conventions
17. Service-to-Service Communication
18. Test Standard
19. New Service Onboarding
20. Secrets Management
21. Distributed Tracing
22. Distributed Transaction and Compensation
23. Prometheus Label and Cardinality Rules
24. Database Isolation Strategy
25. Infrastructure Requirements
26. Compliance Verification
27. Transition Backlog (per-service existing drift)

---

## 1. DOMAIN BOUNDARIES AND SERVICE ISOLATION

### 1.1 Service registry

All service identities, ports, databases, and call boundaries are maintained in
`standards/SERVICE_REGISTRY.md`. This file references it but does not duplicate it.

### 1.2 Boundary rules

- A service MUST NOT connect to another service's database.
- A service MUST NOT import Python modules from another service's package.
- A service MUST NOT own business logic that belongs to another domain.
- Cross-domain data is exchanged exclusively via HTTP or Kafka events.
- Integration concerns (Excel, Telegram, email, SMS, etc.) MUST NOT be absorbed
  into a domain service. They live in their own integration services.
- Locked call boundaries in SERVICE_REGISTRY.md are immutable without a new ADR.

---

## 2. TECHNOLOGY STACK

All services MUST use this stack. Deviations require a `standards/DECISIONS.md` entry.

```
Runtime         : Python 3.12+
Framework       : FastAPI (async ASGI)
ORM             : SQLAlchemy 2.0 (async)
DB Driver       : asyncpg
Migrations      : Alembic (one independent chain per service)
Database        : PostgreSQL 16+
ID Generation   : ULID via python-ulid (26-character string)
Async HTTP      : httpx.AsyncClient
Validation      : Pydantic v2 + pydantic-settings
Broker Client   : confluent-kafka
Tracing         : OpenTelemetry (see §21)
Shared Auth     : packages/platform-auth
Shared Utils    : packages/platform-common
Testing         : pytest + pytest-asyncio (asyncio_mode=auto)
Test DB         : testcontainers[postgres]
Linting         : ruff
Type Checking   : mypy (strict)
```

---

## 3. REQUIRED FILE STRUCTURE

Every service MUST contain these files. Missing required files are a defect.

```
services/{service-name}/
├── Dockerfile
├── .env.example                  # all env vars documented, no real secrets
├── alembic.ini
├── pyproject.toml
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
└── src/{service_module}/
    ├── __init__.py
    ├── auth.py                   # inbound JWT verification, AuthContext
    ├── broker.py                 # AbstractBroker + environment resolution
    ├── config.py                 # pydantic-settings, prod safety validators
    ├── database.py               # engine, session factory, get_session
    ├── entrypoints/
    │   ├── api.py                # uvicorn entrypoint
    │   └── worker.py             # outbox + domain worker entrypoints
    ├── enums.py                  # domain enums
    ├── errors.py                 # ProblemDetailError + exception handlers
    ├── main.py                   # FastAPI app factory
    ├── middleware.py             # RequestIdMiddleware, PrometheusMiddleware
    ├── models.py                 # SQLAlchemy ORM models
    ├── observability.py          # setup_logging + Prometheus metrics
    ├── routers/
    │   ├── health.py             # /health, /ready, /metrics
    │   └── ...                   # domain routers
    ├── schemas.py                # Pydantic request/response schemas
    ├── worker_heartbeats.py      # heartbeat write + read helpers
    └── workers/
        └── outbox_relay.py       # transactional outbox relay
```

Services that call other services MUST also have:
```
    ├── http_clients.py           # shared httpx client lifecycle
    └── clients/
        └── {target}_client.py   # one file per downstream service
```

---

## 4. AUTHENTICATION

### 4.1 Production target (RS256 / JWKS)

```
Algorithm    : RS256
Sole signer  : the auth authority service (identity-service)
Verification : JWKS endpoint served by the auth authority
Issuer       : lojinext-platform
Audience     : lojinext-platform
```

Required env vars (prod):
```
# Hostname and port reference the auth authority service
# Concrete values come from standards/SERVICE_REGISTRY.md
{SVC}_AUTH_JWT_ALGORITHM=RS256
{SVC}_AUTH_ISSUER=lojinext-platform
{SVC}_AUTH_AUDIENCE=lojinext-platform
{SVC}_AUTH_JWKS_URL=http://identity-api:8105/.well-known/jwks.json
{SVC}_AUTH_SERVICE_TOKEN_URL=http://identity-api:8105/auth/v1/token/service
{SVC}_AUTH_SERVICE_CLIENT_ID={service-name}
{SVC}_AUTH_SERVICE_CLIENT_SECRET=${SERVICE_CLIENT_SECRET}
```

### 4.2 JWKS key loading MUST be async

The JWKS key provider MUST use async HTTP (httpx) for fetching keys.
`urllib.request.urlopen` and all synchronous I/O are forbidden in the JWKS
loading path because they block the async event loop during request handling.

Cache TTL expiry and unknown `kid` triggers MUST NOT cause synchronous network I/O.

### 4.3 Transition bridge — PLATFORM_JWT_SECRET (temporary)

`PLATFORM_JWT_SECRET` enables HS256 across services during the RS256 migration.

Enforcement rules in `config.py` via `model_validator`:

| Environment | PLATFORM_JWT_SECRET set | Required behavior              |
|-------------|-------------------------|--------------------------------|
| `prod`      | yes                     | Startup MUST raise ValueError  |
| non-prod    | yes                     | Log WARNING, continue          |
| any         | no                      | Normal operation               |

This bridge MUST NOT be present in any prod deployment.
See §27 for bridge removal conditions.

### 4.4 Inbound token verification — canonical pattern

Every service MUST use this exact function shape in `auth.py`:

```python
def _platform_auth_settings(*, audience: str | None = None) -> AuthSettings:
    effective_audience = settings.auth_audience or audience or None
    return AuthSettings(
        algorithm=settings.auth_jwt_algorithm,
        shared_secret=(
            settings.resolved_auth_jwt_secret
            if settings.auth_jwt_algorithm.upper().startswith("HS")
            else None
        ),
        issuer=settings.auth_issuer or None,
        audience=effective_audience,
        public_key=settings.auth_public_key or None,
        private_key=settings.auth_private_key or None,
        jwks_url=settings.auth_jwks_url or None,
        jwks_cache_ttl_seconds=settings.auth_jwks_cache_ttl_seconds,
    )
```

### 4.5 Service-to-service token acquisition

Services obtain outbound tokens from the auth authority service:
```
POST /auth/v1/token/service
Body: {"client_id": "...", "client_secret": "..."}
```

Every service MUST declare at module level in `auth.py`:
```python
_SERVICE_TOKEN_CACHE = ServiceTokenCache()
```

### 4.6 AuthContext — standard shape

```python
@dataclass(frozen=True)
class AuthContext:
    actor_id: str             # ULID — always present
    role: str                 # PlatformRole string value
    service_name: str | None = None  # set only when role == SERVICE

    @property
    def is_super_admin(self) -> bool:
        return self.role == PlatformRole.SUPER_ADMIN

    @property
    def is_service(self) -> bool:
        return self.role == PlatformRole.SERVICE
```

MUST NOT add `is_admin`, `actor_type`, or other role-hiding properties.
Role checks MUST use `PlatformRole` enum values directly.

---

## 5. ROLE STANDARD

### 5.1 Canonical vocabulary — the only source of truth

```python
# packages/platform-auth/src/platform_auth/roles.py
class PlatformRole(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    MANAGER     = "MANAGER"
    OPERATOR    = "OPERATOR"
    SERVICE     = "SERVICE"

class PlatformActorType(StrEnum):  # for audit logs and timeline entries
    SYSTEM  = "SYSTEM"
    SERVICE = "SERVICE"
    USER    = "USER"
    DRIVER  = "DRIVER"
```

No service MUST define its own role enum.
`PlatformRole` and `PlatformActorType` are imported directly from platform-auth.

### 5.2 Endpoint access matrix

| Endpoint type              | Allowed roles              |
|----------------------------|----------------------------|
| Public `/api/v1/*`         | `SUPER_ADMIN`, `MANAGER`   |
| Hard delete                | `SUPER_ADMIN` only         |
| Internal `/internal/v1/*`  | `SERVICE` only             |
| `/health`, `/ready`, `/metrics` | No auth required      |

---

## 6. ERROR RESPONSE FORMAT

### 6.1 All non-2xx responses MUST use `application/problem+json`

```json
{
  "type":       "https://errors.lojinext.com/TRIP_NOT_FOUND",
  "title":      "Trip not found",
  "status":     404,
  "detail":     "No trip exists with id 01HX7Y...",
  "instance":   "/api/v1/trips/01HX7Y...",
  "code":       "TRIP_NOT_FOUND",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "errors":     []
}
```

Rules:
- `type` MUST be `https://errors.lojinext.com/{CODE}`.
- `code` is always required.
- `detail` MUST be `str`. MUST NOT be `None` or omitted.
- `instance` is always the request path.
- `request_id` is always the `X-Request-Id` from the request.
- `errors` is an empty list when not a validation error.

### 6.2 ProblemDetailError base class

```python
class ProblemDetailError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str,           # str, never None
        instance: str = "",
        errors: list[dict] | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.instance = instance
        self.errors = errors or []
        super().__init__(detail)
```

### 6.3 HTTP status code matrix

| Condition                        | Status | Code                        |
|----------------------------------|--------|-----------------------------|
| Missing Authorization header     | 401    | `AUTH_REQUIRED`             |
| Invalid or expired token         | 401    | `AUTH_INVALID`             |
| Insufficient role                | 403    | `INSUFFICIENT_ROLE`         |
| Internal call without SERVICE    | 403    | `UNAUTHORIZED_INTERNAL_CALL`|
| Entity not found                 | 404    | `{ENTITY}_NOT_FOUND`        |
| Business rule violation          | 422    | `{ENTITY}_{RULE}`           |
| Pydantic validation failure      | 422    | `VALIDATION_ERROR`          |
| `If-Match` header missing        | 428    | `IF_MATCH_REQUIRED`         |
| ETag mismatch                    | 412    | `VERSION_MISMATCH`          |
| Downstream service unreachable   | 503    | `DEPENDENCY_UNAVAILABLE`    |
| Duplicate idempotency key        | 409    | `DUPLICATE_REQUEST`         |

### 6.4 Validation error shape

```json
{
  "errors": [
    {"field": "driver_id", "code": "missing", "message": "Field required"},
    {"field": "gross_weight_kg", "code": "greater_than", "message": "Input should be greater than 0"}
  ]
}
```

---

## 7. API DESIGN AND VERSIONING

### 7.1 URL structure

```
/api/v1/{resource}        Public API — MANAGER, SUPER_ADMIN
/internal/v1/{resource}   Service-to-service — SERVICE role only
/health                   Liveness — no auth
/ready                    Readiness — no auth
/metrics                  Prometheus scrape — no auth
```

`/health`, `/ready`, `/metrics` MUST be at the root. No version prefix.

### 7.2 Router registration rule

```python
# CORRECT — no prefix, every decorator writes the full path
router = APIRouter(tags=["trips"])

@router.post("/api/v1/trips")
@router.get("/api/v1/trips/{trip_id}")

# WRONG — prefix + relative path = silent double-prefix bug
router = APIRouter(prefix="/api/v1/trips")
@router.post("")   # silently becomes /api/v1/trips/api/v1/trips
```

Health router MUST declare `APIRouter()` with no prefix.

### 7.3 Idempotency

Create (POST) endpoints MUST support idempotency:
- Canonical header: `Idempotency-Key`
- Legacy alias: `X-Idempotency-Key` (read-only, canonical takes precedence if both present)
- On duplicate: return the original response body and ETag. Do not return 409.
- Records expire after a configurable TTL (default 24h).

### 7.4 ETag and optimistic locking

Mutation endpoints (PUT, PATCH, DELETE, state-change POST) MUST require `If-Match`.
- Missing `If-Match`: 428 `IF_MATCH_REQUIRED`
- Stale `If-Match`: 412 `VERSION_MISMATCH`
- ETag format: `"{version}"` — quoted integer string. MUST be consistent across all endpoints.

### 7.5 Soft delete vs. hard delete

- Soft delete sets `soft_deleted_at_utc`. The row stays in the database.
- Soft-deleted records MUST be excluded from list responses by default.
- Clients that need tombstones MUST pass an explicit filter.
- Hard delete physically removes the row.
  It MUST write an immutable audit record before deletion.
  It MUST be restricted to `SUPER_ADMIN`.
  It MUST require a `reason` string in the request body.

---

## 8. PAGINATION

### 8.1 Offset pagination — for admin lists with a known total

```
Query params : page (int ≥ 1), per_page (int ≥ 1, ≤ 200)
Default      : page=1, per_page=50

Response:
{
  "items":    [...],
  "page":     1,
  "per_page": 50,
  "total":    342
}
```

### 8.2 Cursor pagination — for large datasets and internal streaming

```
Query params : cursor (str | null), limit (int ≥ 1, ≤ 200)
Default      : cursor=null, limit=50

Response:
{
  "items":       [...],
  "next_cursor": "01HX...",   // null when last page
  "limit":       50
}
```

Cursor MUST be an opaque ULID-based string. MUST NOT be an offset integer.

### 8.3 Rule

Do not mix both styles on the same endpoint.
Public admin endpoints use offset. Internal streaming endpoints use cursor.

---

## 9. OUTBOX MODEL

### 9.1 Canonical field set

Every service that publishes events MUST use this exact schema:

```
Field                 Type             Notes
outbox_id             String(26) PK    ULID
aggregate_type        String(16)       domain entity type
aggregate_id          String(26)       Subject aggregate's ULID
aggregate_version     Integer          Optimistic lock version at publish time
event_name            String(80)       dot.separated naming — see §9.4
event_version         Integer          Payload schema version (default 1)
payload_json          Text             JSON string. NOT JSONB — portability required
partition_key         String(100)      Kafka partition key
publish_status        String(16)       PENDING | PUBLISHING | PUBLISHED | FAILED | DEAD_LETTER
attempt_count         Integer          Default 0
last_error_code       String(100)      Nullable
next_attempt_at_utc   Timestamptz      Nullable
claim_token           String(50)       Nullable — set when status = PUBLISHING
claim_expires_at_utc  Timestamptz      Nullable — set when status = PUBLISHING
claimed_by_worker     String(50)       Nullable
created_at_utc        Timestamptz
published_at_utc      Timestamptz      Nullable — set when PUBLISHED
```

### 9.2 State machine

```
PENDING ──► PUBLISHING ──► PUBLISHED
                      └──► FAILED ──► (retry back to PENDING)
                                └──► DEAD_LETTER (max attempts reached)
```

Relay rules:
1. Query `PENDING` and `FAILED` rows where `next_attempt_at_utc <= now`.
2. Before publishing: set `PUBLISHING`, `claim_token`, `claim_expires_at_utc`. Commit.
3. Each row is committed independently. Batch commits are forbidden.
4. On success: set `PUBLISHED`, `published_at_utc`. Commit.
5. On failure: set `FAILED`, `last_error_code`, backoff `next_attempt_at_utc`. Commit.
6. At start of each relay cycle: recover stale `PUBLISHING` rows
   (where `claim_expires_at_utc < now`) back to `PENDING`.

### 9.3 Retry backoff

```
Attempt 1 : immediate
Attempt 2 : +30 seconds
Attempt 3 : +2 minutes
Attempt 4 : +10 minutes
Attempt 5 : +1 hour → DEAD_LETTER if still fails
```

### 9.4 Event naming

```
Pattern : {aggregate}.{past_tense_verb}
Topic   : {aggregate}.events.v1

Examples:
  trip.created          → topic: trip.events.v1
  driver.activated      → topic: driver.events.v1
  vehicle.registered    → topic: fleet.events.v1
```

---

## 10. HEALTH, READY, AND METRICS ENDPOINTS

### 10.1 /health — liveness probe

```
GET /health
Auth: none
Always returns 200 while the process is running.
```

Response:
```json
{"status": "ok", "service": "{service-name}"}
```

MUST NOT check the database or any downstream service.

### 10.2 /ready — readiness probe

```
GET /ready
Auth: none
200 = all checks pass
503 = any check fails
```

Required checks by service category:

| Check               | Required for                     |
|---------------------|----------------------------------|
| `database`          | every service                    |
| `broker`            | services that publish to Kafka   |
| `auth`              | services using JWKS verification |
| `{worker_name}`     | services with background workers |
| `{downstream_name}` | services that call others        |

Worker heartbeat staleness threshold: 120 seconds.

### 10.3 /metrics — Prometheus scrape

```
GET /metrics
Auth: none
Protected by network isolation (reverse proxy). Not exposed to public internet.
Content-Type: text/plain (Prometheus exposition format)
```

### 10.4 Mounting rule

Health router MUST be mounted with no prefix.

---

## 11. MIDDLEWARE

### 11.1 Required middleware, in this order

```python
app.add_middleware(RequestIdMiddleware)
app.add_middleware(PrometheusMiddleware)
```

### 11.2 RequestIdMiddleware — MUST be pure ASGI

`BaseHTTPMiddleware.call_next()` wraps the inner app in a thread pool executor.
This conflicts with asyncpg's connection model and causes hangs under load.
All services MUST use the pure ASGI implementation. `BaseHTTPMiddleware` is forbidden.

```python
class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        request_id = (
            headers.get(b"x-request-id", b"").decode() or str(uuid.uuid4())
        )
        correlation_id = (
            headers.get(b"x-correlation-id", b"").decode() or request_id
        )
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id
        scope["state"]["correlation_id"] = correlation_id

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                hdrs = list(message.get("headers", []))
                hdrs.append((b"x-request-id", request_id.encode()))
                hdrs.append((b"x-correlation-id", correlation_id.encode()))
                message = {**message, "headers": hdrs}
            await send(message)

        await self.app(scope, receive, send_with_headers)
```

### 11.3 Required response headers

Every response MUST include:
- `X-Request-Id` — inbound value or generated UUID
- `X-Correlation-Id` — inbound value or defaults to `X-Request-Id`

---

## 12. LOGGING

### 12.1 Format — structured JSON to stdout

Every log line is a single JSON object. One object per line. No plain-text logging.

Required fields in every log entry:
```json
{
  "timestamp":  "2026-04-05T12:00:00.000000+00:00",
  "level":      "INFO",
  "service":    "{service-name}",
  "logger":     "{service_module}.{submodule}",
  "message":    "Published outbox event",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

`request_id` is only present when processing an HTTP request.

### 12.2 setup_logging — canonical implementation

Called once at startup in `main.py` or entrypoint:

```python
def setup_logging(level: str = "INFO") -> None:
    import json as json_mod

    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            entry: dict = {
                "timestamp": datetime.now(UTC).isoformat(),
                "level":     record.levelname,
                "service":   settings.service_name,
                "logger":    record.name,
                "message":   record.getMessage(),
            }
            if hasattr(record, "request_id"):
                entry["request_id"] = record.request_id
            if record.exc_info:
                entry["exception"] = self.formatException(record.exc_info)
            return json_mod.dumps(entry, ensure_ascii=False)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
```

### 12.3 Logger naming

```python
# Module-level loggers — explicit name required
logger = logging.getLogger("{service_module}.{submodule}")

# __name__ is acceptable only inside domain/ and providers/ subdirectories
```

### 12.4 Log level guide

| Level    | Use for                                                    |
|----------|------------------------------------------------------------|
| DEBUG    | Detailed internal state — development only                 |
| INFO     | Normal operation milestones (worker loop, event published) |
| WARNING  | Recoverable issues (circuit breaker opened, retry queued)  |
| ERROR    | Exceptions that affect a request or worker cycle           |
| CRITICAL | Unrecoverable process-level failures                       |

MUST NOT log: passwords, JWT secrets, encryption keys, or any PII.

---

## 13. OBSERVABILITY — PROMETHEUS METRICS

### 13.1 Required metrics — every service

```
{svc}_http_requests_total           Counter   labels: method, endpoint, status_code
{svc}_http_request_duration_seconds Histogram labels: method, endpoint
{svc}_outbox_published_total        Counter   labels: event_name
{svc}_outbox_dead_letter_total      Counter
```

### 13.2 Metric naming convention

```
{service_prefix}_{noun}_{unit_or_aggregation}

service_prefix : derived from service module name
unit           : _seconds (duration), _bytes (size), _total (counter)
```

### 13.3 Required business metrics

Each service MUST define counters for:
- Primary entity creation
- Primary entity terminal state transitions (completed, cancelled, deactivated)
- Dependency failures (circuit breaker opens, downstream timeouts)

These counters MUST exist before a service is considered production-ready.

---

## 14. DATABASE AND MIGRATIONS

### 14.1 Session management

```python
# CORRECT — async context manager
async with async_session_factory() as session:
    result = await session.execute(select(Entity).where(...))
    await session.commit()

# CORRECT — eager load relations before use
stmt = (
    select(Entity)
    .options(selectinload(Entity.relation))
    .where(Entity.id == entity_id)
)

# WRONG — lazy relation access in async context
entity = await session.get(Entity, entity_id)
_ = entity.relation   # raises MissingGreenlet
```

Session factory MUST use `expire_on_commit=False`:
```python
async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)
```

### 14.2 Connection pool defaults

```python
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)
```

### 14.3 Migration rules

- Every migration MUST have both `upgrade()` and `downgrade()`.
- Breaking changes require two phases:
  Phase 1 — add new column, keep old (backward-compatible, deploy first).
  Phase 2 — remove old column (separate migration, deployed after Phase 1 is stable).
- Backfill scripts MUST be separate files. MUST NOT run inside Alembic.
- Backfill scripts MUST default to `--dry-run`. `--apply` is explicit.
- Backfill scripts MUST be idempotent.

### 14.4 Model conventions

```python
# Primary key — ULID, 26 characters
id: Mapped[str] = mapped_column(String(26), primary_key=True)

# Timestamps — always UTC, always timezone-aware, always _utc suffix
created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

# Soft delete — timestamp, not a boolean
soft_deleted_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

# Table naming — service-prefix required
# Example: trip_trips, trip_outbox, fleet_vehicles, driver_drivers

# DEPRECATED — do not use
datetime.utcnow()   # use datetime.now(UTC) instead
```

---

## 15. MESSAGE BROKER

### 15.1 Environment-based broker resolution

```python
def resolve_broker(env: str, kafka_servers: str) -> AbstractBroker:
    match env:
        case "prod":  return KafkaBroker(bootstrap_servers=kafka_servers)
        case "test":  return NoopBroker()    # silent, no network
        case _:       return LogBroker()     # logs to stdout
```

### 15.2 AbstractBroker interface

```python
class AbstractBroker:
    async def publish(self, topic: str, key: str, value: str) -> None: ...
    async def check_health(self) -> None: ...  # raises on failure
    async def close(self) -> None: ...
```

### 15.3 Production safety

- `PLAINTEXT` Kafka protocol in `prod` environment MUST raise at startup.
- `allow_plaintext_in_prod` defaults to `False`.
- If `ENVIRONMENT=prod`, the flag is ignored and treated as `False` unconditionally.
- Kafka broker MUST NOT run in `dev-container` mode in production.
  Dev-container mode is RAM-only and loses all data on restart.

---

## 16. ID AND TIMESTAMP CONVENTIONS

### 16.1 Identifiers — ULID everywhere

- All primary keys, foreign references, outbox IDs, and audit IDs MUST be ULID.
- ULID: 26 characters, URL-safe, lexicographically sortable, millisecond-precision.
- UUID and integer sequences MUST NOT be used as public identifiers.

```python
from ulid import ULID
new_id = str(ULID())  # → "01HX7Y..."
```

### 16.2 Timestamps — UTC, timezone-aware, _utc suffix

```python
from datetime import UTC, datetime

# CORRECT
now = datetime.now(UTC)
column = mapped_column(DateTime(timezone=True), nullable=False)
field_name = "created_at_utc"

# WRONG
datetime.utcnow()              # deprecated, returns naive datetime
DateTime(timezone=False)       # loses timezone information
field_name = "created_at"      # missing _utc suffix
```

---

## 17. SERVICE-TO-SERVICE COMMUNICATION

### 17.1 HTTP client — per-call client, explicit timeout

```python
async with httpx.AsyncClient(
    timeout=httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=60.0),
) as client:
    token = await issue_service_token(audience="{target-service}")
    resp = await client.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
```

### 17.2 Circuit breaker — required for every downstream client

```
Threshold : 5 consecutive failures → OPEN
Half-open : probe after 30 seconds
OPEN      : raises DependencyUnavailableError → HTTP 503 to caller
```

### 17.3 Retry policy

HTTP calls at request time: NO retry. Fail fast, return 503.
Retries happen through the outbox relay. Direct HTTP retries are forbidden.

### 17.4 No optimistic fallback

When a downstream service is unavailable, the calling service MUST return 503.
Setting a dependent validation to `True` on downstream failure (optimistic fallback)
is forbidden. Unavailable means unavailable — the caller must not guess.

### 17.5 Internal endpoint authentication

All `/internal/v1/*` endpoints MUST require `SERVICE` role authentication.
No internal endpoint may be unauthenticated regardless of network isolation.
Network isolation is defense-in-depth, not a substitute for auth.

### 17.6 Locked service call boundaries

See `standards/SERVICE_REGISTRY.md` for the locked call boundary table.
Changes require a new ADR in `docs/adr/`.

---

## 18. TEST STANDARD

### 18.1 Test directory layout

```
tests/unit/         Pure Python — no DB, no network
tests/integration/  testcontainers Postgres + real Alembic migrations
tests/contract/     Endpoint contract tests (path, auth, response shape)
tests/smoke/        Process alive, routes registered
```

### 18.2 Mandatory test coverage per service

| Concern                                   | Location              |
|-------------------------------------------|-----------------------|
| Prod bridge rejection (PLATFORM_JWT_SECRET) | `test_config.py`    |
| Exact registered route paths               | `test_runtime.py`    |
| `/health`, `/ready`, `/metrics` at root    | `test_contract.py`   |
| Auth: missing header → 401                 | `test_contract.py`   |
| Auth: wrong role → 403                     | `test_contract.py`   |
| Outbox: PENDING → PUBLISHING → PUBLISHED   | `test_workers.py`    |
| `alembic upgrade head` + `downgrade -1`    | `test_migrations.py` |

### 18.3 Non-trivial test definition

A test is valid when:
- It asserts the response body, not only the HTTP status code.
- It covers at least one failure path in addition to the happy path.
- It cannot pass by deleting the code under test.
- Mocks are used only for external dependencies (network, time), not for the database.

### 18.4 Fixture convention

```python
@pytest.fixture(scope="session")
async def engine():
    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url().replace("postgresql://", "postgresql+asyncpg://")
        eng = create_async_engine(url)
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield eng
        await eng.dispose()

@pytest.fixture
async def session(engine):
    async with AsyncSession(engine) as s:
        yield s
        await s.rollback()
```

### 18.5 CI gates — all four must pass before merge

```yaml
- ruff check src/ tests/
- mypy src/{service_module}/ --ignore-missing-imports
- alembic upgrade head
- pytest tests/ -v --tb=short
```

A service with failing lint or mypy MUST NOT be merged into `dev` or `main`.

---

## 19. NEW SERVICE ONBOARDING

Follow this checklist in order. The service MUST NOT merge into `dev`
until every item is checked.

### 19.1 Pre-code decision record

Before writing any code, add an entry to `standards/DECISIONS.md` covering:
- Service name and identifier
- Port assignment — MUST NOT conflict with SERVICE_REGISTRY.md
- Database name
- Domain responsibility statement
- Upstream services this service will call
- Downstream services that will call this service
- Kafka topics this service will publish to (if any)

Update the service registry table in `standards/SERVICE_REGISTRY.md`.

### 19.2 Required files at PR creation

The PR that introduces the service MUST include all files from §3.
Each file MUST satisfy the rules in its corresponding section.

### 19.3 Infrastructure additions

- Add the service to the production Docker Compose file.
- Add the service database to `init-db.sh`.
- Add the service upstream to `nginx.conf.template`.
- Register the service in the auth authority's service client list.
- Update `standards/SERVICE_REGISTRY.md` with the new service entry.
- Verify the new service appears in MANIFEST.yaml.

### 19.4 CI workflow additions

- Add a CI job for the new service.
- The job MUST include: ruff, mypy, alembic upgrade, pytest.

### 19.5 Production readiness gate

A new service is not production-ready until all of the following are true:

- All §18.2 mandatory tests pass in CI.
- `docker compose up` brings the service to healthy within 60 seconds.
- `/ready` returns 200 with all checks passing.
- Outbox relay publishes at least one event end-to-end in smoke test.
- RS256 / JWKS auth verified in smoke test — bridge not required.
- The service is registered in `standards/SERVICE_REGISTRY.md`.
- The service is registered in the auth authority's service client list.
- The service has a Dockerfile with non-root user and healthcheck.
- Worker entrypoints have graceful shutdown (SIGTERM/SIGINT handlers).
- No `PLATFORM_JWT_SECRET` required at startup.

---

## 20. SECRETS MANAGEMENT

### 20.1 Rules

- Secrets MUST NOT appear in source code, commit history, or log output.
- `.env.example` MUST document every env var with a placeholder value, never a real secret.
- Default secret values in `config.py` MUST be clearly marked as dev-only
  and MUST be rejected in `prod`.

### 20.2 Prod rejection — required in every config.py

Every service MUST validate production safety at startup:

```python
@model_validator(mode="after")
def _validate_prod_safety(self) -> "Settings":
    if self.environment == "prod":
        if self.platform_jwt_secret:
            raise ValueError(
                "PLATFORM_JWT_SECRET must not be set in production."
            )
        if "dev-secret" in (self.auth_jwt_secret or "").lower():
            raise ValueError(
                "Default development JWT secret detected in production."
            )
    return self
```

### 20.3 Secret categories

| Category                  | Scope         | Rotation              |
|---------------------------|---------------|-----------------------|
| Database passwords        | Infrastructure| Manual                |
| Key encryption keys (KEK) | identity-only | Versioned, supported  |
| Service client secrets    | Per service   | Via identity rotation |
| Signing keys (RS256)      | identity-only | Via JWKS, no downtime |
| Transition bridge secrets | Temporary     | Removed after migration|

---

## 21. DISTRIBUTED TRACING

### 21.1 Requirement

Every service MUST participate in distributed tracing using OpenTelemetry.
A request that crosses service boundaries MUST carry a trace context from
origin to completion.

### 21.2 Trace propagation

- W3C TraceContext headers (`traceparent`, `tracestate`) MUST be propagated
  on all HTTP service-to-service calls and Kafka event payloads.
- The `X-Request-Id` header (see §11.3) MUST be included as a span attribute.

### 21.3 Span naming

```
Pattern: {http_method} {route_template}

Examples:
  POST /api/v1/trips
  GET /api/v1/trips/{trip_id}
  POST /internal/v1/routes/resolve
```

Spans MUST use the route template, NOT the raw URL path.
This prevents cardinality explosion in the tracing backend.

### 21.4 Outbox event tracing

When an outbox event is published, the current trace context MUST be embedded
in the event payload. The consuming service MUST continue the trace when processing
the event.

### 21.5 Implementation

```
Library      : opentelemetry-api + opentelemetry-sdk
Instrumention: opentelemetry-instrumentation-fastapi
Exporter     : OTLP (to Jaeger, Tempo, or compatible backend)
Propagation  : W3C TraceContext
```

### 21.6 Open decisions

These choices MUST be resolved before tracing is deployed:
- Exporter backend selection (Jaeger vs Tempo vs other)
- Sampling strategy (head-based vs tail-based)
- Trace retention period
- Resource requirements for the tracing backend

Add a `standards/DECISIONS.md` entry when resolved.

---

## 22. DISTRIBUTED TRANSACTION AND COMPENSATION

### 22.1 Principle

Any operation that spans multiple services MUST define a compensation plan.
If one step fails, previously completed steps MUST be reversible.

### 22.2 Pattern selection

| Scenario                        | Pattern         |
|---------------------------------|-----------------|
| Single downstream call + outbox | Outbox + retry  |
| Sequential multi-service call   | Orchestration saga |
| Event-driven multi-service flow | Choreography saga  |

### 22.3 Compensation event format

```
Event name  : {aggregate}.compensation.{action}
Topic       : {aggregate}.events.v1
Payload     : { original_event_id, compensation_reason, rollback_data }
```

### 22.4 Rules

- Every multi-service operation MUST document which step triggers compensation
  and what each compensation action does.
- Compensation actions MUST be idempotent.
- Compensation MUST NOT require human intervention for known failure modes.
- The outbox model (§9) applies to compensation events as well.

### 22.5 Saga state tracking

For orchestration sagas, the orchestrator service MUST persist saga state:
```
saga_id             : ULID
saga_type           : String
current_step        : String
status              : PENDING | COMPLETED | COMPENSATING | COMPENSATED | FAILED
started_at_utc      : Timestamptz
completed_at_utc    : Timestamptz (nullable)
compensation_reason : Text (nullable)
```

### 22.6 Open decisions

These choices MUST be resolved before a multi-service saga is implemented:
- Which service acts as saga orchestrator for each multi-service flow
- Whether saga state lives in a dedicated table or reuses the outbox model
- Maximum allowed saga duration before automatic compensation

Add a `standards/DECISIONS.md` entry when resolved.

---

## 23. PROMETHEUS LABEL AND CARDINALITY RULES

### 23.1 Route template labels — mandatory

The `endpoint` label in Prometheus metrics MUST use the FastAPI route template,
NOT the raw request path.

```python
# CORRECT — use route template
REQUEST_DURATION.labels(endpoint="/api/v1/trips/{trip_id}", ...)

# WRONG — raw path causes cardinality explosion
REQUEST_DURATION.labels(endpoint="/api/v1/trips/01HX7Y...", ...)
```

### 23.2 Cardinality limits

- Maximum unique label combinations per metric: 1,000
- Any label value that grows with data (IDs, names, timestamps) is forbidden.
- High-cardinality data belongs in logs and traces, not in metrics.

### 23.3 Label naming

```
{service_prefix}_{metric_name}
```

Labels: `method`, `endpoint` (template), `status_code`.

### 23.4 Enforcement

A metric that exceeds the cardinality limit is a defect.
CI SHOULD include a cardinality check for registered metrics.

---

## 24. DATABASE ISOLATION STRATEGY

### 24.1 Principle

Each service owns its data exclusively. Database isolation levels vary by environment
but the ownership boundary is always enforced.

### 24.2 Production

- Each service MUST have its own PostgreSQL instance (or managed database).
- Shared PostgreSQL instances across services are forbidden in production.
- Connection from one service to another service's database is a critical security violation.

### 24.3 Development and staging

- Shared PostgreSQL instance is acceptable with separate database names.
- The `init-db.sh` script MUST create all registered databases.
- Connection pool limits MUST be set per service to prevent resource starvation:
  ```
  pool_size=10, max_overflow=20 per service
  ```

### 24.4 Migration isolation

- A service's Alembic migrations MUST NOT affect another service's schema.
- Migration scripts MUST run within the service's own database only.
- Long-running migrations MUST be designed to avoid locking tables used by other services
  (even on shared instances during development).

### 24.5 Backup and recovery

- Production: each database instance has its own backup schedule.
- Minimum: daily full backup, point-in-time recovery enabled.
- Backup verification (restore test) MUST run at least monthly.

### 24.6 Migration path

Current state: all services share a single PostgreSQL instance with separate database names.
This is acceptable for development (see §24.3) but MUST be resolved before production.

Migration steps (in order):
1. Provision separate PostgreSQL instances per service in the target environment.
2. Migrate data using `pg_dump` / `pg_restore` per database.
3. Update connection strings in service config.
4. Verify all services connect to their own instance.
5. Remove shared PostgreSQL instance.

Each step requires a DECISIONS.md entry and a dedicated task.

---

## 25. INFRASTRUCTURE REQUIREMENTS

### 25.1 Container orchestration

Production deployment MUST use a container orchestration platform
(Kubernetes, ECS, or equivalent). Docker Compose is acceptable for development
and testing only.

### 25.2 Resource limits

Every container MUST declare resource limits:
```
Memory limit   : defined per service (minimum 256MB)
CPU limit      : defined per service
Restart policy : on-failure with backoff
```

### 25.3 Service mesh

When the platform has more than 5 services, a service mesh or equivalent
traffic management layer SHOULD be evaluated. Requirements:
- Mutual TLS between services
- Automatic retry and circuit breaking at infrastructure level
- Traffic observability (per-service dashboards)

### 25.4 High availability

- Stateful services (databases, message broker) MUST run with replication.
- Single-instance deployments are acceptable in development only.
- RTO target: defined per service. RPO target: defined per service.

### 25.5 Disaster recovery

- Infrastructure MUST be defined as code (Terraform, Helm, Docker Compose).
- Infrastructure definitions live in the repository under `deploy/`.
- Manual infrastructure changes outside the repository are forbidden.

---

## 26. COMPLIANCE VERIFICATION

### 26.1 Principle

Standards without verification are suggestions. This section defines
how compliance is checked automatically.

### 26.2 Required file check (CI)

Every service MUST pass a compliance check that verifies:
- All files in §3 exist
- `auth.py` contains `_platform_auth_settings`
- `config.py` contains `_validate_prod_safety`
- `middleware.py` does NOT contain `BaseHTTPMiddleware`
- `routers/health.py` exists with `/health`, `/ready`, `/metrics`
- `models.py` uses `String(26)` primary keys
- `.env.example` exists and has no real secrets

### 26.3 Pattern check (CI)

- No `datetime.utcnow()` in any source file
- No `BaseHTTPMiddleware` in any middleware file
- No `JSONB` column type for outbox `payload_json`
- All internal endpoints have auth dependency
- ETag format is consistent across all mutation endpoints

### 26.4 Compliance script location

```
scripts/check_standard_compliance.py
```

This script runs in CI and MUST pass before merge into `dev` or `main`.

### 26.5 Manual review checklist

For changes that automated checks cannot verify:
- Saga compensation plan documented (if multi-service)
- Trace context propagation implemented
- Circuit breaker configured for new downstream calls
- Cardinality impact assessed for new metrics

---

## 27. TRANSITION BACKLOG

Known deviations from this standard are tracked in `standards/KNOWN_ISSUES.md`
with a section per service. Each service repair task MUST address the items listed
for that service.

### Bridge removal conditions

All four must be true before removing the PLATFORM_JWT_SECRET bridge:

- All services verified with RS256 + JWKS in smoke test
- All services obtain service tokens from the auth authority
- `PLATFORM_JWT_SECRET` absent from all prod env files
- Full smoke test passes with `PLATFORM_JWT_SECRET` unset

---

## AGENT QUICK-REFERENCE

Read before every repair task, without exception.

```
Before touching code:
  □ standards/DECISIONS.md            — do not re-make locked decisions
  □ standards/PLATFORM_STANDARD.md   — this file
  □ standards/KNOWN_ISSUES.md         — do not re-report open issues
  □ standards/SERVICE_REGISTRY.md     — service identities and boundaries
  □ TASKS/ history for target service — do not redo completed work

During patch:
  □ Roles use PlatformRole — no local role enum
  □ Error detail is str, never None
  □ Error type URL is https://errors.lojinext.com/{CODE}
  □ /health, /ready, /metrics at root path — no /v1 prefix
  □ Router has no prefix — full absolute path in every decorator
  □ Middleware is pure ASGI — BaseHTTPMiddleware is forbidden
  □ JWKS loading is async — no urllib/sync I/O
  □ Internal endpoints require SERVICE role auth
  □ Prometheus endpoint label uses route template, not raw path
  □ No optimistic fallback on downstream failure
  □ Outbox has all claim fields
  □ Timestamps use datetime.now(UTC) — datetime.utcnow() is forbidden
  □ PLATFORM_JWT_SECRET prod rejection in config.py
  □ Worker entrypoints have graceful shutdown

After patch:
  □ ruff check src tests — passes clean
  □ mypy — passes clean
  □ pytest — all tests pass with non-trivial assertions
  □ Exact route paths verified in test_runtime.py
  □ Known issues for this service updated in standards/KNOWN_ISSUES.md
