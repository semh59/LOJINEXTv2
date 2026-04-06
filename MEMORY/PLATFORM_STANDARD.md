# PLATFORM_STANDARD.md
# LOJINEXTv2 — Platform Engineering Standard

**Language rule:** All backend code, comments, commit messages, and documentation MUST be in English.
Frontend/UI supports both English and Turkish at the presentation layer.

**This file is binding.** No agent touches any service without reading it first.
This file supersedes any per-service pattern that contradicts it.
"It was done this way before" is not a justification for a non-standard pattern.

Last updated: 2026-04-05
Version: 2.0.0

---

## GOVERNANCE

### Who owns this file
This file is owned by the project. Any change requires a `MEMORY/DECISIONS.md`
entry with: date, reason, and the section number changed. No undated changes.

### How to update
1. Write the decision in `MEMORY/DECISIONS.md` first.
2. Update this file.
3. Update `MEMORY/KNOWN_ISSUES.md` if the change reveals existing drift.
4. On the next repair task for each affected service, the agent applies the change.

### What "binding" means
- A pattern that contradicts this standard is a defect, not a style choice.
- An agent that defers to "how it was done before" instead of this file is wrong.

---

## TABLE OF CONTENTS

1.  Service Registry and Domain Boundaries
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
21. Transition Backlog (per-service existing drift)

---

## 1. SERVICE REGISTRY AND DOMAIN BOUNDARIES

| Service          | service_name     | Port | Database         | Domain Owner                    |
|------------------|------------------|------|------------------|---------------------------------|
| identity-service | identity-service | 8105 | identity_service | Authentication, users, JWT keys |
| trip-service     | trip-service     | 8101 | trip_service     | Trip lifecycle                  |
| location-service | location-service | 8103 | location_service | Routes, location authority      |
| driver-service   | driver-service   | 8104 | driver_service   | Driver master data              |
| fleet-service    | fleet-service    | 8102 | fleet_service    | Vehicles, trailers              |

### Boundary rules

- A service MUST NOT connect to another service's database.
- A service MUST NOT import Python modules from another service's package.
- A service MUST NOT own business logic that belongs to another domain.
- Cross-domain data is exchanged exclusively via HTTP or Kafka events.
- Excel, Telegram, and other integration concerns MUST NOT be absorbed into a domain service.
- ADR-001 is locked: Trip calls Fleet for reference validation.
  Fleet calls Driver internally. Trip MUST NOT call Driver directly.

---

## 2. TECHNOLOGY STACK

All services MUST use this stack. Deviations require a `MEMORY/DECISIONS.md` entry.

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
Sole signer  : identity-service
Verification : JWKS endpoint
JWKS URL     : http://identity-api:8105/.well-known/jwks.json
Issuer       : lojinext-platform
Audience     : lojinext-platform
```

Required env vars (prod):
```
{SVC}_AUTH_JWT_ALGORITHM=RS256
{SVC}_AUTH_ISSUER=lojinext-platform
{SVC}_AUTH_AUDIENCE=lojinext-platform
{SVC}_AUTH_JWKS_URL=http://identity-api:8105/.well-known/jwks.json
{SVC}_AUTH_SERVICE_TOKEN_URL=http://identity-api:8105/auth/v1/token/service
{SVC}_AUTH_SERVICE_CLIENT_ID={service-name}
{SVC}_AUTH_SERVICE_CLIENT_SECRET=${SERVICE_CLIENT_SECRET}
```

### 4.2 Transition bridge — PLATFORM_JWT_SECRET (temporary)

`PLATFORM_JWT_SECRET` enables HS256 across services during the RS256 migration.

Enforcement rules in `config.py` via `model_validator`:

| Environment | PLATFORM_JWT_SECRET set | Required behavior              |
|-------------|-------------------------|--------------------------------|
| `prod`      | yes                     | Startup MUST raise ValueError  |
| non-prod    | yes                     | Log WARNING, continue          |
| any         | no                      | Normal operation               |

This bridge MUST NOT be present in any prod deployment.
See section 21 for bridge removal conditions.

### 4.3 Inbound token verification — canonical pattern

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

### 4.4 Service-to-service token acquisition

Services obtain outbound tokens from identity-service:
```
POST /auth/v1/token/service
Body: {"client_id": "...", "client_secret": "..."}
```

Every service MUST declare at module level in `auth.py`:
```python
_SERVICE_TOKEN_CACHE = ServiceTokenCache()
```

### 4.5 AuthContext — standard shape

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
`PlatformRole` and `PlatformActorType` are imported directly.

### 5.2 Endpoint access matrix

| Endpoint type              | Allowed roles              |
|----------------------------|----------------------------|
| Public `/api/v1/*`         | `SUPER_ADMIN`, `MANAGER`   |
| Hard delete                | `SUPER_ADMIN` only         |
| Internal `/internal/v1/*`  | `SERVICE` only             |
| `/health`, `/ready`, `/metrics` | No auth required      |

### 5.3 Current role drift (fix during service repair)

| Service          | Violation                                | Fix                            |
|------------------|------------------------------------------|--------------------------------|
| fleet-service    | `ActorType.ADMIN` not in PlatformRole    | Map to `MANAGER`/`SUPER_ADMIN` |
| driver-service   | `INTERNAL_SERVICE` not in PlatformRole  | Replace with `SERVICE`         |
| location-service | Inline string constants, no enum         | Import and use `PlatformRole`  |

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
  Current per-service URLs (`https://trip-service/errors/...`) are non-standard — fix during repair.
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
| Invalid or expired token         | 401    | `AUTH_INVALID`              |
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
- ETag format: `"{version}"` — quoted integer string.

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
aggregate_type        String(16)       TRIP | DRIVER | FLEET | USER | LOCATION
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
  trip.completed        → topic: trip.events.v1
  driver.activated      → topic: driver.events.v1
  vehicle.registered    → topic: fleet.events.v1
```

### 9.5 Current outbox drift (fix during service repair)

| Service          | Missing or wrong fields                                                  |
|------------------|--------------------------------------------------------------------------|
| fleet-service    | Missing: `claim_token`, `claim_expires_at_utc`, `claimed_by_worker`; `payload_json` is JSONB (must be Text) |
| driver-service   | `retry_count` → `attempt_count`; `last_error Text` → `last_error_code String(100)`; missing: `aggregate_version`, `partition_key`, claim fields |
| identity-service | Missing: `aggregate_version`, `partition_key`, claim fields              |

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

Response shape (200):
```json
{
  "status": "ready",
  "checks": {
    "database":          "ok",
    "broker":            "ok",
    "auth":              "ok",
    "fleet_service":     "ok",
    "location_service":  "ok",
    "enrichment_worker": "ok",
    "outbox_worker":     "ok"
  }
}
```

Response shape (503):
```json
{
  "status": "not_ready",
  "checks": {
    "database": "ok",
    "broker":   "unavailable"
  }
}
```

Worker heartbeat staleness threshold: 120 seconds.

### 10.3 /metrics — Prometheus scrape

```
GET /metrics
Auth: none
Protected by network isolation (reverse proxy). Not exposed to public internet.
Content-Type: text/plain (Prometheus exposition format)
```

### 10.4 Mounting rule

Health router MUST be mounted with no prefix:
```python
# CORRECT
app.include_router(health_router)            # router has APIRouter() — no prefix

# WRONG
app.include_router(health_router, prefix="/v1")  # produces /v1/health
```

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
All services MUST use the pure ASGI implementation.

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
  "service":    "trip-service",
  "logger":     "trip_service.workers.outbox_relay",
  "message":    "Published outbox event",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

`request_id` is only present when processing an HTTP request.

On exception, add:
```json
{"exception": "Traceback (most recent call last):\n  ..."}
```

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
logger = logging.getLogger("trip_service.outbox_relay")
logger = logging.getLogger("fleet_service.clients.driver_client")

# __name__ is acceptable only inside domain/ and providers/ subdirectories
logger = logging.getLogger(__name__)   # OK inside location_service/providers/
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

service_prefix : trip | fleet | driver | location | identity
unit           : _seconds (duration), _bytes (size), _total (counter)

Examples:
  trip_created_total
  trip_enrichment_duration_seconds
  fleet_vehicle_create_total
  fleet_http_breaker_open_total
  driver_outbox_published_total
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
    result = await session.execute(select(TripTrip).where(...))
    await session.commit()

# CORRECT — eager load relations before use
stmt = (
    select(TripTrip)
    .options(selectinload(TripTrip.timeline))
    .where(TripTrip.id == trip_id)
)

# WRONG — lazy relation access in async context
trip = await session.get(TripTrip, trip_id)
_ = trip.timeline   # raises MissingGreenlet
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
- Backfill scripts that encounter unexpected data MUST exit non-zero and report.

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
# trip_trips, trip_outbox, trip_audit_log
# fleet_vehicles, fleet_trailers, fleet_outbox
# driver_drivers, driver_outbox

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

### 17.4 Locked service call boundaries (ADR-001)

```
trip-service    → location-service   POST /internal/v1/routes/resolve
trip-service    → fleet-service      POST /internal/v1/trip-references/validate
fleet-service   → driver-service     POST /internal/v1/drivers/eligibility/check
driver-service  → trip-service       GET  /internal/v1/trips/driver-check/{driver_id}
```

These are fixed. Changes require a new ADR in `docs/adr/`.

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

Before writing any code, add an entry to `MEMORY/DECISIONS.md` covering:
- Service name and identifier
- Port assignment — MUST NOT conflict with section 1 registry
- Database name
- Domain responsibility statement
- Upstream services this service will call
- Downstream services that will call this service
- Kafka topics this service will publish to (if any)

Update the service registry table in section 1 of this file.

### 19.2 Required files at PR creation

The PR that introduces the service MUST include all files from section 3.
Each file MUST satisfy:

| File               | Requirement                                                    |
|--------------------|----------------------------------------------------------------|
| `auth.py`          | Canonical `_platform_auth_settings` pattern                   |
| `config.py`        | `PLATFORM_JWT_SECRET` prod rejection validator                 |
| `errors.py`        | `ProblemDetailError` with `detail: str` (not `str | None`)    |
| `middleware.py`    | Pure ASGI `RequestIdMiddleware` (not `BaseHTTPMiddleware`)     |
| `models.py`        | ULID PKs, `_utc` timestamps, service-prefixed table names      |
| `routers/health.py`| `/health`, `/ready`, `/metrics` at root (no prefix)           |
| `observability.py` | `setup_logging` + required Prometheus metrics                  |
| `enums.py`         | Imports `PlatformRole` — does not define its own role enum     |
| `001_initial_schema.py` | Both `upgrade()` and `downgrade()` written               |
| `.env.example`     | All env vars documented, no real secrets                       |

### 19.3 Infrastructure additions

- Add the service to `deploy/compose/trip-location/docker-compose.prod.yml`
- Add the service to `deploy/compose/trip-location/docker-compose.ci.yml`
- Add the service DB to `deploy/compose/trip-location/init-db.sh`
- Add the service upstream to `nginx/nginx.conf.template`
- Register the service in identity-service `IDENTITY_SERVICE_CLIENTS`

### 19.4 CI workflow additions

- Add a job for the new service in `.github/workflows/trip-location-verify.yml`
- Add the service path to `on.push.paths` and `on.pull_request.paths`
- The job MUST include: ruff, mypy, alembic upgrade, pytest

### 19.5 Production readiness gate

A new service is not production-ready until all of the following are true:
- [ ] All section 18.2 mandatory tests pass in CI
- [ ] `docker compose up` brings the service to healthy within 60 seconds
- [ ] `/ready` returns 200 with all checks passing
- [ ] Outbox relay publishes at least one event end-to-end in smoke test
- [ ] RS256 / JWKS auth verified in smoke test — bridge not required
- [ ] Backfill script exists if the initial migration creates data gaps
- [ ] No `PLATFORM_JWT_SECRET` required at startup

---

## 20. SECRETS MANAGEMENT

### 20.1 Rules

- Secrets MUST NOT appear in source code, commit history, or log output.
- `.env.example` MUST document every env var with a placeholder value, never a real secret.
- Default secret values in `config.py` MUST be clearly marked as dev-only
  and MUST be rejected in `prod`.

### 20.2 Prod rejection — required in every config.py

```python
from pydantic import model_validator

@model_validator(mode="after")
def _validate_prod_safety(self) -> "Settings":
    if self.environment == "prod":
        if self.platform_jwt_secret:
            raise ValueError(
                "PLATFORM_JWT_SECRET must not be set in production. "
                "Configure RS256 + JWKS through identity-service."
            )
        if "dev-secret" in (self.auth_jwt_secret or "").lower():
            raise ValueError(
                "Default development JWT secret detected in production environment."
            )
        if self.allow_plaintext_in_prod:
            raise ValueError(
                "allow_plaintext_in_prod must be false in production."
            )
    elif self.platform_jwt_secret:
        import logging
        logging.getLogger(f"{self.service_name}.config").warning(
            "PLATFORM_JWT_SECRET bridge is active. "
            "This is a temporary transition mode. Do not deploy to production."
        )
    return self
```

### 20.3 Secret categories

| Secret                             | Scope             | Notes                             |
|------------------------------------|-------------------|-----------------------------------|
| `POSTGRES_PASSWORD`                | Infrastructure    | Manual rotation                   |
| `IDENTITY_KEY_ENCRYPTION_KEY_B64`  | identity-service  | Versioned KEK, rotation supported |
| `{SVC}_AUTH_SERVICE_CLIENT_SECRET` | Per service       | Registered in identity-service    |
| `PLATFORM_JWT_SECRET`              | Transition only   | Removed once RS256 is complete    |
| RS256 signing keys                 | identity-service  | Rotated via JWKS without downtime |

---

## 21. TRANSITION BACKLOG

These are confirmed deviations from this standard in the current codebase.
Each service repair task MUST address the items listed for that service.
Items are checked off when the fix is merged and CI passes.

### identity-service
- [ ] Outbox: add `aggregate_version`, `partition_key`, claim fields
- [ ] Outbox relay: add stale-claim recovery

### trip-service
- [x] Router prefix fix
- [x] Health endpoints at root path
- [x] PLATFORM_JWT_SECRET prod rejection
- [x] `/ready` includes Fleet and Location probes
- [x] platform-auth + platform-common as runtime deps
- [x] Outbox per-event commit + stale-claim recovery
- [ ] Error `type` URL → `https://errors.lojinext.com/{CODE}`

### location-service
- [ ] Health router: remove `prefix="/v1"`
- [ ] Roles: replace inline string constants with `PlatformRole` imports
- [ ] Outbox: add claim fields
- [ ] Config: add `PLATFORM_JWT_SECRET` prod rejection
- [ ] Config: add `allow_plaintext_in_prod` flag and enforce it
- [ ] Error `type` URL → `https://errors.lojinext.com/{CODE}`

### driver-service
- [ ] Middleware: `BaseHTTPMiddleware` → pure ASGI
- [ ] Health router: missing — create with `/health`, `/ready`, `/metrics` at root
- [ ] Roles: replace `INTERNAL_SERVICE` with `SERVICE`
- [ ] Outbox: `retry_count` → `attempt_count`
- [ ] Outbox: `last_error Text` → `last_error_code String(100)`
- [ ] Outbox: add `aggregate_version`, `partition_key`, claim fields
- [ ] Config: add `PLATFORM_JWT_SECRET` prod rejection
- [ ] Error `type` URL → `https://errors.lojinext.com/{CODE}`

### fleet-service
- [ ] Middleware: `BaseHTTPMiddleware` → pure ASGI
- [ ] Health router: remove `prefix="/v1"`
- [ ] Roles: `ActorType.ADMIN` → align with `PlatformRole`
- [ ] Outbox: `payload_json` JSONB → Text
- [ ] Outbox: add `claim_token`, `claim_expires_at_utc`, `claimed_by_worker`
- [ ] Outbox relay: add stale-claim recovery
- [ ] Errors: `detail: str | None` → `detail: str`
- [ ] Config: add `PLATFORM_JWT_SECRET` prod rejection
- [ ] ISSUE-003: `initial_spec` fields silently ignored on create
- [ ] Error `type` URL → `https://errors.lojinext.com/{CODE}`

### Bridge removal conditions — all four must be true before removing

- [ ] All 5 services verified with RS256 + JWKS in smoke test
- [ ] All 5 services obtain service tokens from identity-service
- [ ] `PLATFORM_JWT_SECRET` absent from all prod env files
- [ ] Full smoke test passes with `PLATFORM_JWT_SECRET` unset

Only after all four: remove `resolved_auth_jwt_secret`, bridge logic,
and `PLATFORM_JWT_SECRET` from all config surfaces.

---

## AGENT QUICK-REFERENCE

Read before every repair task, without exception.

```
Before touching code:
  □ MEMORY/DECISIONS.md           — do not re-make locked decisions
  □ MEMORY/PLATFORM_STANDARD.md  — this file
  □ MEMORY/KNOWN_ISSUES.md        — do not re-report open issues as new findings
  □ TASKS/ history for target service — do not redo completed work

During patch:
  □ Roles use PlatformRole — no local role enum
  □ Error detail is str, never None
  □ Error type URL is https://errors.lojinext.com/{CODE}
  □ /health, /ready, /metrics are at root path — no /v1 prefix
  □ Router has no prefix — every decorator writes the full absolute path
  □ Middleware is pure ASGI — BaseHTTPMiddleware is forbidden
  □ Every migration has upgrade() and downgrade()
  □ Backfill script: --dry-run default, idempotent, exits non-zero on unexpected data
  □ Outbox has all claim fields
  □ Timestamps use datetime.now(UTC) — datetime.utcnow() is forbidden
  □ PLATFORM_JWT_SECRET prod rejection in config.py
  □ Logger names follow {service_module}.{submodule} convention

After patch:
  □ ruff check src tests — passes clean
  □ mypy — passes clean
  □ pytest — all tests pass with non-trivial assertions
  □ Exact route paths verified in test_runtime.py
  □ Section 21 items for this service updated
```
