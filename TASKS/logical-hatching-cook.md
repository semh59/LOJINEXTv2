# TASK-0053 — Identity Service: Full Security & Architecture Hardening

**Context:**  
A deep forensic audit of identity-service revealed 6 confirmed bugs (2 critical security bypasses, 1 race condition, 3 architecture defects) and 10 medium/high findings. All issues are treated as critical per user instruction. This task fixes every confirmed issue end-to-end, adds Redis for rate limiting + token revocation, implements refresh token family tracking, and brings all admin endpoints to platform standard.

**Next Task ID after this:** TASK-0054

---

## Scope

All fixes in a single PR against `services/identity-service/`. One Alembic migration chain. One Redis dependency. Zero breaking changes to the public API contract.

---

## Critical Files

| File | Role |
|------|------|
| `src/identity_service/token_service.py` | BUG-2, BUG-3, BUG-5, H-2, H-3 |
| `src/identity_service/routers/auth.py` | BUG-1, BUG-4, H-1, H-4, M-6 |
| `src/identity_service/routers/admin.py` | BUG-6, M-5, M-6 |
| `src/identity_service/models.py` | BUG-2 (family_id), M-2 (deactivated_at_utc) |
| `src/identity_service/config.py` | Redis settings, rate limit config |
| `src/identity_service/main.py` | H-2 (executor shutdown), M-1 (dialect fix) |
| `src/identity_service/auth.py` | H-4 (jti blocklist check) |
| `src/identity_service/middleware.py` | BUG-1/H-1 (rate limit middleware) |
| `src/identity_service/entrypoints/outbox_worker.py` | H-5 (signal handling) |
| `src/identity_service/workers/outbox_relay.py` | H-5 (shutdown event) |
| `alembic/versions/010_security_hardening.py` | BUG-2 migration (family_id + invalidation) |
| `pyproject.toml` | redis[asyncio], slowapi dependencies |
| `tests/test_auth.py` | New security test cases |
| `tests/test_security_boundary.py` | Audience bypass, retired key, rate limit tests |

---

## Implementation Steps

### STEP 1 — Redis Infrastructure

**File:** `src/identity_service/redis_client.py` (new file)

```python
import redis.asyncio as aioredis
from identity_service.config import settings

_redis: aioredis.Redis | None = None

async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis

async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
```

**`config.py` additions:**
```python
redis_url: str = "redis://localhost:6379/0"
rate_limit_login_per_minute: int = 10
rate_limit_login_failures_before_lockout: int = 5
rate_limit_login_lockout_seconds: int = 900  # 15 min
rate_limit_service_token_per_minute: int = 30
access_token_blocklist_ttl_seconds: int = 950  # slightly > access_token_ttl_seconds
```

**`main.py` lifespan — add Redis shutdown:**
```python
from identity_service.redis_client import close_redis
from identity_service.token_service import _executor

@asynccontextmanager
async def lifespan(app):
    ...bootstrap...
    yield
    await engine.dispose()
    await close_redis()
    _executor.shutdown(wait=True)    # H-2 fix
```

**`pyproject.toml` additions:**
```
"redis[asyncio]>=5.0.0",
```

---

### STEP 2 — Rate Limiting Middleware (BUG-1, H-1)

**File:** `src/identity_service/middleware.py` — add `RateLimitMiddleware`

Implementation uses Redis for distributed per-IP + per-username tracking:

```python
class RateLimitMiddleware(BaseHTTPMiddleware):
    RATE_LIMITED_PATHS = {
        "/auth/v1/login": ("login", settings.rate_limit_login_per_minute),
        "/auth/v1/token/service": ("service_token", settings.rate_limit_service_token_per_minute),
    }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path not in self.RATE_LIMITED_PATHS:
            return await call_next(request)

        key_prefix, limit = self.RATE_LIMITED_PATHS[path]
        client_ip = request.client.host or "unknown"
        redis = await get_redis()

        # Per-IP sliding window
        ip_key = f"rl:{key_prefix}:ip:{client_ip}"
        count = await redis.incr(ip_key)
        if count == 1:
            await redis.expire(ip_key, 60)
        if count > limit:
            return JSONResponse(
                status_code=429,
                content={"error_code": "RATE_LIMITED", "message": "Too many requests.", ...},
                headers={"Retry-After": "60"},
            )

        # For login: check per-username lockout BEFORE calling next
        if path == "/auth/v1/login":
            body_bytes = await request.body()
            # reconstruct body for downstream
            ...parse username from body...
            lockout_key = f"rl:login:lockout:{username}"
            if await redis.exists(lockout_key):
                return JSONResponse(status_code=429, content={...lockout message...})

        response = await call_next(request)

        # Track failures for lockout (login only)
        if path == "/auth/v1/login" and response.status_code == 401:
            fail_key = f"rl:login:fail:{username}"
            failures = await redis.incr(fail_key)
            if failures == 1:
                await redis.expire(fail_key, settings.rate_limit_login_lockout_seconds)
            if failures >= settings.rate_limit_login_failures_before_lockout:
                await redis.setex(lockout_key, settings.rate_limit_login_lockout_seconds, "1")

        return response
```

**`main.py`:** Add `app.add_middleware(RateLimitMiddleware)` after existing middleware.

**Note on body reading:** FastAPI's `BaseHTTPMiddleware` does not allow re-reading the body natively. Use a custom ASGI middleware or cache the body in `request.state` using a small `receive` wrapper. The `starlette` `Request.body()` call with `_body` caching pattern handles this.

---

### STEP 3 — Audience Bypass Fix (BUG-4)

**File:** `src/identity_service/token_service.py:591-599`

**Current (broken):**
```python
if audience and audience != settings.auth_audience:
    if settings.auth_strict_audience_check:
        raise ValueError("Strict Mode: ...")
    if audience not in settings.bootstrap_service_names:
        raise ValueError("...")
    # FALLS THROUGH → issues token with foreign audience
```

**Fix — reject all cross-audience requests unless strict mode explicitly allows it:**
```python
if audience and audience != settings.auth_audience:
    if not settings.auth_strict_audience_check:
        raise ValueError(
            "Cross-service audience tokens are disabled. "
            "Set IDENTITY_AUTH_STRICT_AUDIENCE_CHECK=true to enable."
        )
    if audience not in settings.bootstrap_service_names:
        raise ValueError(
            "Requested audience is not a registered service."
        )
```

This inverts the guard: strict=False → reject, strict=True + valid audience → permit. The default (`auth_strict_audience_check=False`) now means "same-platform audience only" which is the safe default.

**`config.py`:** Rename/clarify the setting name, add to prod validation check that it is explicitly set (not left at default).

---

### STEP 4 — Retired Key Validation Fix (BUG-5)

**File:** `src/identity_service/token_service.py:614-629`

Add after `signing_key = await session.get(...)`:

```python
if signing_key is None:
    raise ValueError("Signing key not found.")
if signing_key.retired_at_utc is not None:
    raise ValueError("Token signed with a retired key.")
```

One line change. No migration needed.

---

### STEP 5 — Refresh Token Family Tracking (BUG-2)

#### 5a. Migration: `alembic/versions/010_security_hardening.py`

```python
def upgrade():
    # Add family_id column (nullable initially)
    op.add_column(
        "identity_refresh_tokens",
        sa.Column("family_id", sa.String(26), nullable=True),
    )
    # Invalidate all legacy tokens (NULL family_id = no family tracking)
    op.execute(
        "UPDATE identity_refresh_tokens SET revoked_at_utc = NOW() "
        "WHERE revoked_at_utc IS NULL AND family_id IS NULL"
    )
    # Make nullable=False with default (only affects new rows going forward)
    # Can't set NOT NULL without data — leave nullable, enforce in app layer
    op.create_index("ix_identity_refresh_tokens_family", "identity_refresh_tokens", ["family_id"])

def downgrade():
    op.drop_index("ix_identity_refresh_tokens_family", "identity_refresh_tokens")
    op.drop_column("identity_refresh_tokens", "family_id")
```

#### 5b. Model: `models.py`

```python
family_id: Mapped[Optional[str]] = mapped_column(String(26), nullable=True, index=True)
```

#### 5c. `token_service.py` — `issue_token_pair`

```python
async def issue_token_pair(
    session, user, *, family_id: str | None = None
) -> dict:
    ...
    new_family_id = family_id or _new_ulid()   # start new family or continue
    refresh_row = IdentityRefreshTokenModel(
        ...
        family_id=new_family_id,
    )
```

#### 5d. `token_service.py` — `rotate_refresh_token`

```python
async def rotate_refresh_token(session, raw_refresh_token):
    token_hash = _hash_token(raw_refresh_token)
    result = await session.execute(
        select(IdentityRefreshTokenModel)
        .where(IdentityRefreshTokenModel.token_hash == token_hash)
    )
    refresh_row = result.scalar_one_or_none()

    # STOLEN TOKEN DETECTION: already-revoked token reuse → nuke the family
    if refresh_row is not None and refresh_row.revoked_at_utc is not None:
        if refresh_row.family_id:
            await session.execute(
                update(IdentityRefreshTokenModel)
                .where(
                    IdentityRefreshTokenModel.family_id == refresh_row.family_id,
                    IdentityRefreshTokenModel.revoked_at_utc.is_(None),
                )
                .values(revoked_at_utc=_now_utc())
            )
        raise ValueError("STOLEN_TOKEN: Token reuse detected. All sessions invalidated.")

    if (
        refresh_row is None
        or _as_utc(refresh_row.expires_at_utc) <= _now_utc()
    ):
        raise ValueError("Refresh token is invalid or expired.")

    user = await session.get(IdentityUserModel, refresh_row.user_id)
    if user is None or not user.is_active:
        raise ValueError("Refresh token owner is inactive.")

    refresh_row.revoked_at_utc = _now_utc()
    # Pass family_id to continue the family chain
    token_pair = await issue_token_pair(session, user, family_id=refresh_row.family_id)
    await session.flush()
    return token_pair
```

---

### STEP 6 — Access Token Revocation via Redis JTI Blocklist (H-4)

#### 6a. `src/identity_service/blocklist.py` (new file)

```python
from identity_service.redis_client import get_redis
from identity_service.config import settings

async def block_token(jti: str, ttl_seconds: int | None = None) -> None:
    redis = await get_redis()
    ttl = ttl_seconds or settings.access_token_blocklist_ttl_seconds
    await redis.setex(f"jti:blocked:{jti}", ttl, "1")

async def is_token_blocked(jti: str) -> bool:
    redis = await get_redis()
    return bool(await redis.exists(f"jti:blocked:{jti}"))
```

#### 6b. `token_service.py` — `decode_access_token`

After verifying the token:
```python
claims = verify_token(token, auth_settings)
# JTI blocklist check
jti = getattr(claims, "jti", None) or claims.get("jti")
if jti and await is_token_blocked(jti):
    raise ValueError("Token has been revoked.")
return claims
```

**Note:** `verify_token` returns a claims object. Need to check how `jti` is exposed — may need `claims.model_dump()["jti"]` or dict access depending on `platform_auth` API.

#### 6c. `routers/auth.py` — `logout`

```python
@router.post("/auth/v1/logout", status_code=200)
async def logout(body: LogoutRequest, session=..., authorization=Header(None)):
    await revoke_refresh_token(session, body.refresh_token)
    # Also blocklist the current access token if provided
    if authorization:
        try:
            token = parse_bearer_token(authorization)
            header = jwt.get_unverified_header(token)
            payload = jwt.decode(token, options={"verify_signature": False})
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            ttl = max(0, exp - int(datetime.now(UTC).timestamp()))
            if jti and ttl > 0:
                await block_token(jti, ttl_seconds=ttl)
        except Exception:
            pass  # best-effort; refresh token is already revoked
    await session.commit()
    return {"status": "LOGGED_OUT"}
```

#### 6d. `routers/admin.py` — user deactivation

In `update_user`, when `body.is_active is False`:
```python
if body.is_active is False and user.is_active:
    user.deactivated_at_utc = _now_utc()
    # Revoke all active refresh tokens for this user
    await session.execute(
        update(IdentityRefreshTokenModel)
        .where(
            IdentityRefreshTokenModel.user_id == user.user_id,
            IdentityRefreshTokenModel.revoked_at_utc.is_(None),
        )
        .values(revoked_at_utc=_now_utc())
    )
    # Note: existing access tokens expire naturally within 15 min (documented risk)
```

---

### STEP 7 — `ensure_active_signing_key` Race Fix (BUG-3)

**File:** `token_service.py:153-181`

Add `with_for_update(skip_locked=False)` to the initial select so concurrent requests serialize on key creation:

```python
result = await session.execute(
    select(IdentitySigningKeyModel)
    .where(IdentitySigningKeyModel.is_active.is_(True))
    .order_by(IdentitySigningKeyModel.created_at_utc.desc())
    .with_for_update()   # serialize concurrent key creation
)
key = result.scalars().first()
if key is not None:
    return key
# ... create new key
```

This is safe because the hot path (key exists) acquires and releases immediately. Cold path (key creation) is serialized.

---

### STEP 8 — Bootstrap Dialect Check Fix (M-1)

**File:** `main.py:36-39`

```python
# Current (deprecated pattern):
bind = session.get_bind()
if bind is not None and bind.dialect.name == "postgresql":

# Fix (use module-level engine):
from identity_service.database import engine
if engine.dialect.name == "postgresql":
    await session.execute(text("SELECT pg_advisory_xact_lock(78216)"))
```

Remove the `bind` variable entirely.

---

### STEP 9 — Private Helper Promotion (BUG-6)

**File:** `token_service.py`

Promote `_now_utc`, `_new_ulid`, `_write_audit` to public API (remove underscore prefix):

```python
# token_service.py
def now_utc() -> datetime: ...
def new_ulid() -> str: ...
async def write_audit(...) -> None: ...
```

**File:** `routers/admin.py` — update imports:
```python
from identity_service.token_service import (
    now_utc,
    new_ulid,
    write_audit,
    ...
)
```

---

### STEP 10 — Admin List Pagination (M-5)

**File:** `routers/admin.py` — `list_users` and `list_audit_logs`

Add cursor-based pagination per Platform Standard §8:

```python
@router.get("/v1/users", response_model=UserListResponse)
async def list_users(
    username: str | None = None,
    cursor: str | None = None,
    limit: int = Query(50, le=200),
    ...
):
    query = select(IdentityUserModel).order_by(IdentityUserModel.user_id.asc()).limit(limit + 1)
    if cursor:
        query = query.where(IdentityUserModel.user_id > cursor)
    if username:
        ...
    rows = result.scalars().all()
    next_cursor = rows[-1].user_id if len(rows) > limit else None
    return {"items": [UserResponse(...)  for r in rows[:limit]], "next_cursor": next_cursor}
```

Add `UserListResponse` and `AuditListResponse` to `schemas.py`.

---

### STEP 11 — Platform-Standard Error Responses (M-6)

**File:** `src/identity_service/errors.py` (new file)

```python
from datetime import UTC, datetime
from fastapi import Request
from fastapi.responses import JSONResponse
from identity_service.observability import correlation_id

def platform_error(
    status_code: int,
    error_code: str,
    message: str,
    request_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": error_code,
            "message": message,
            "request_id": request_id or correlation_id.get(""),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
```

Replace all `raise HTTPException(status_code=X, detail="...")` in `routers/auth.py` and `routers/admin.py` with `raise platform_error(...)` — or add a global exception handler to `main.py` that wraps `HTTPException` into the platform format.

**Recommended approach:** Global exception handler in `main.py`:

```python
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return platform_error(exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail),
                          request_id=getattr(request.state, "correlation_id", None))

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return platform_error(422, "VALIDATION_ERROR", str(exc.errors()),
                          request_id=getattr(request.state, "correlation_id", None))
```

---

### STEP 12 — `deactivated_at_utc` Column (M-2)

**File:** `models.py` — `IdentityUserModel`

```python
deactivated_at_utc: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), nullable=True
)
```

Add to migration `010_security_hardening.py`:
```python
op.add_column("identity_users", sa.Column("deactivated_at_utc", sa.DateTime(timezone=True), nullable=True))
```

---

### STEP 13 — Outbox Worker Signal Handling (H-5)

**File:** `entrypoints/outbox_worker.py`

```python
import asyncio
import signal

async def _run() -> None:
    broker = create_broker(settings.resolved_broker_backend)
    shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_event.set)

    try:
        await run_outbox_relay(broker, shutdown_event=shutdown_event)
    finally:
        await broker.close()
```

**File:** `workers/outbox_relay.py` — `run_outbox_relay` signature:

```python
async def run_outbox_relay(broker: EventBroker, *, shutdown_event: asyncio.Event | None = None) -> None:
    while True:
        if shutdown_event and shutdown_event.is_set():
            logger.info("Outbox relay: shutdown signal received, exiting cleanly.")
            return
        ...
        await asyncio.sleep(settings.outbox_poll_interval_seconds)
```

---

### STEP 14 — Audit Log & Refresh Token Cleanup Jobs (M-3, M-4)

**File:** `workers/cleanup_worker.py` (new file)

```python
async def run_cleanup(*, shutdown_event: asyncio.Event | None = None) -> None:
    while True:
        if shutdown_event and shutdown_event.is_set():
            return
        await _purge_expired_refresh_tokens()
        await _archive_old_audit_logs()   # or just delete if no archival needed
        await asyncio.sleep(86400)  # run daily

async def _purge_expired_refresh_tokens() -> None:
    cutoff = datetime.now(UTC) - timedelta(days=1)  # grace period after expiry
    async with async_session_factory() as session:
        await session.execute(
            delete(IdentityRefreshTokenModel).where(
                IdentityRefreshTokenModel.expires_at_utc < cutoff
            )
        )
        await session.commit()
```

Run this inside the outbox worker entrypoint as a concurrent task, or add a separate `cleanup_worker` entrypoint.

---

### STEP 15 — New Tests

**File:** `tests/test_security_boundary.py` — add:

1. `test_audience_bypass_rejected_without_strict_mode` — service-A requests audience=service-B with `strict=False`, expects 400.
2. `test_audience_permitted_with_strict_mode` — same with `strict=True`, expects 200.
3. `test_retired_key_rejected` — sign token with key, retire key, verify decode raises.
4. `test_refresh_token_reuse_invalidates_family` — rotate token, reuse original → expects 401 + all family members revoked.
5. `test_rate_limit_login_ip` — 11 requests to `/auth/v1/login` from same IP → 429 on 11th.
6. `test_login_lockout_after_failures` — 5 failed logins → lockout, correct password returns 429.
7. `test_logout_blocklists_access_token` — login, logout with Authorization header, immediate re-use of access token → 401.
8. `test_user_deactivation_revokes_refresh_tokens` — create user, login, deactivate via admin → refresh returns 401.

**File:** `tests/test_workers.py` — add:

9. `test_outbox_worker_respects_shutdown_event` — set shutdown_event immediately, verify worker exits after current sleep.

---

## Migration File: `alembic/versions/010_security_hardening.py`

Single migration combining all schema changes:

```
1. ADD identity_refresh_tokens.family_id VARCHAR(26) nullable
2. UPDATE identity_refresh_tokens SET revoked_at_utc = NOW() WHERE revoked_at_utc IS NULL  (BUG-2: invalidate legacy tokens)
3. CREATE INDEX ix_identity_refresh_tokens_family ON identity_refresh_tokens(family_id)
4. ADD identity_users.deactivated_at_utc TIMESTAMP WITH TIME ZONE nullable  (M-2)
```

Downgrade: reverse all four in reverse order.

---

## Config Changes Summary

`config.py` additions:
```
redis_url: str = "redis://localhost:6379/0"
rate_limit_login_per_minute: int = 10
rate_limit_login_failures_before_lockout: int = 5
rate_limit_login_lockout_seconds: int = 900
rate_limit_service_token_per_minute: int = 30
access_token_blocklist_ttl_seconds: int = 950
```

`validate_prod_settings` additions:
- Reject if `redis_url` is default localhost in prod.
- Warn if `auth_strict_audience_check` is not explicitly set (document intent).

---

## New Files Created

| File | Purpose |
|------|---------|
| `src/identity_service/redis_client.py` | Redis connection management |
| `src/identity_service/blocklist.py` | JTI blocklist read/write |
| `src/identity_service/errors.py` | Platform-standard error response builder |
| `src/identity_service/workers/cleanup_worker.py` | Refresh token + audit log cleanup |
| `alembic/versions/010_security_hardening.py` | DB migration for family_id + deactivated_at_utc |

---

## Verification

```bash
# 1. Run full test suite
cd services/identity-service
pytest -x -v

# 2. Start Redis locally for integration
docker run -d -p 6379:6379 redis:7

# 3. Run specific security tests
pytest tests/test_security_boundary.py -v

# 4. Run migration against test DB
IDENTITY_DATABASE_URL=... alembic upgrade head

# 5. Verify audience bypass is fixed:
# POST /auth/v1/token/service with audience=other-service → must return 400

# 6. Verify rate limiting:
# 11x POST /auth/v1/login → 10 proceed, 11th returns 429

# 7. Verify token family revocation:
# rotate token, reuse original → 401 + DB shows all family members revoked
```

---

## KNOWN_ISSUES entries to add after completion

- H-4 mitigated (Redis blocklist) — close existing gap
- New: Redis is now a hard dependency for identity-service in all envs except `test` (noop mode)

## PROJECT_STATE.md update

- Mark TASK-0053 as completed
- Set next task ID to TASK-0054
