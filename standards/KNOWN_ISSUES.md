# KNOWN_ISSUES.md
# Known Issues

Issues that affect the project as a whole or cross multiple areas.
Issues specific to a single component belong in that component's own docs.
Issues specific to a single task belong in TASKS/<id>/STATE.md.

Issues are never silently deleted.
When resolved: mark resolved, write what fixed it, keep the entry.

---

## How to Write an Issue

```
## [ISSUE-NNN] Short title

- **Discovered:** YYYY-MM-DD, TASK-XXXX
- **Impact:** What breaks or gets harder because of this
- **Status:** open | mitigated | resolved
- **Workaround:** What to do until it is fixed
- **Linked task:** TASK-XXXX or none
- **Resolution:** (fill when resolved — what fixed it)
```

---

## Open

## [ISSUE-001] Location Service repository-wide lint debt outside internal resolve scope

- **Discovered:** 2026-03-27, TASK-0010
- **Impact:** Running `ruff check src tests` in `services/location-service` still fails on pre-existing files unrelated to the new internal resolve endpoint, which blocks a clean repo-wide lint signal for that service.
- **Status:** open
- **Workaround:** Run targeted lint on the internal resolve files added in TASK-0010 until the existing lint findings in other location-service files are cleaned up.
- **Linked task:** TASK-0010
- **Resolution:** 

---

## [ISSUE-002] Docker smoke script returns non-zero due to PowerShell NativeCommandError

- **Discovered:** 2026-03-28, TASK-0014
- **Impact:** `TASKS/TASK-0012/scripts/smoke.ps1` can exit non-zero even when the smoke steps complete, which may cause CI or automation to treat the run as failed.
- **Status:** resolved
- **Workaround:** (resolved)
- **Linked task:** TASK-0017
- **Resolution:** Updated `TASKS/TASK-0012/scripts/smoke.ps1` to suppress PowerShell native-command error records, validate exit codes explicitly, and exit 0 on success.

---

## [ISSUE-004] Redis is now a hard runtime dependency for identity-service

- **Discovered:** 2026-04-08, TASK-0053
- **Impact:** identity-service will not start without a reachable Redis instance in `dev` and `prod` environments. `test` environment uses fakeredis (no real Redis needed).
- **Status:** open
- **Workaround:** Start Redis via `docker run -d -p 6379:6379 redis:7` or set `IDENTITY_REDIS_URL` to a managed Redis URL.
- **Linked task:** TASK-0053
- **Resolution:**

---

## [ISSUE-005] Access token revocation window: 15 minutes after user deactivation

- **Discovered:** 2026-04-08, TASK-0053
- **Impact:** When a user is deactivated via `PATCH /admin/v1/users/{id}`, their existing access tokens remain valid until expiry (up to 15 minutes). JTI blocklist only covers tokens presented at `/auth/v1/logout`. Deactivation does not enumerate and blocklist all live access tokens.
- **Status:** mitigated
- **Workaround:** Deactivation immediately revokes all refresh tokens (prevents new access token issuance). The 15-minute window is the remaining risk. `current_user` dependency re-checks `is_active` from DB on every request, so this only affects service tokens that bypass `current_user`.
- **Linked task:** TASK-0053
- **Resolution:**

---

## Standard Drift — Per-Service

These are confirmed deviations from PLATFORM_STANDARD.md that exist in the current codebase.
Each service repair task MUST address the items listed for that service.
Items are checked off when the fix is merged and CI passes.
This section was migrated from the old PLATFORM_STANDARD.md transition backlog.

### identity-service
- [ ] Outbox: add `aggregate_version`, `partition_key`, claim fields
- [ ] Outbox relay: add stale-claim recovery
- [ ] Middleware: `BaseHTTPMiddleware` → pure ASGI (causes asyncpg connection corruption under concurrency)
- [ ] Outbox `payload_json`: storing `json.dumps()` string in JSONB column — should be dict for JSONB or Text column

### trip-service
- [x] Router prefix fix
- [x] Health endpoints at root path
- [x] PLATFORM_JWT_SECRET prod rejection
- [x] `/ready` includes Fleet and Location probes
- [x] platform-auth + platform-common as runtime deps
- [x] Outbox per-event commit + stale-claim recovery
- [ ] Error `type` URL → `https://errors.lojinext.com/{CODE}`
- [ ] ETag format inconsistency: `service.py` uses `f'"{trip.version}"'` while `trips.py` uses `make_etag(trip.id, trip.version)` — cancel, approve, reject, edit endpoints return 412 on every If-Match
- [ ] Prometheus `endpoint` label uses raw path → cardinality explosion (every trip ID creates new label)
- [ ] cleanup_worker and enrichment_worker missing graceful shutdown (SIGTERM/SIGINT handler)

### location-service
- [ ] Health router: remove `prefix="/v1"`
- [ ] Roles: replace inline string constants with `PlatformRole` imports
- [ ] Outbox: add claim fields
- [ ] Config: add `PLATFORM_JWT_SECRET` prod rejection
- [ ] Config: add `allow_plaintext_in_prod` flag and enforce it
- [ ] Error `type` URL → `https://errors.lojinext.com/{CODE}`
- [ ] Internal endpoints `/internal/v1/routes/resolve` and `/internal/v1/route-pairs/{pair_id}/trip-context` missing auth dependency — SERVICE role check required

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
- [ ] Error `type` URL → `https://errors.lojinext.com/{CODE}`
- [ ] Optimistic fallback on driver-service unavailability returns `driver_valid=True` — violates PLATFORM_STANDARD.md §17.4

### telegram-service
- [ ] `fleet_service_url` field missing from Settings class — every fleet lookup raises AttributeError
- [ ] `by-plate` endpoint not implemented in fleet-service — every plate lookup returns 404
- [ ] Not registered in `IDENTITY_SERVICE_CLIENTS` — all service token requests return 401
- [ ] FSM state stored in memory when `TELEGRAM_REDIS_URL` is empty — all state lost on restart
- [ ] Not registered in MANIFEST.yaml — invisible to agent workflows

### Cross-Service
- [ ] platform-auth JWKS key loading uses `urllib.request.urlopen` (synchronous) — blocks async event loop for 5s on cache miss, affects all consuming services
- [ ] Redpanda runs in `dev-container` mode in docker-compose — all Kafka data lost on container restart
- [ ] All services share single PostgreSQL instance — connection pool exhaustion or migration locking in one service affects all others

### Bridge removal conditions
All four must be true before removing PLATFORM_JWT_SECRET:
- [ ] All services verified with RS256 + JWKS in smoke test
- [ ] All services obtain service tokens from identity-service
- [ ] `PLATFORM_JWT_SECRET` absent from all prod env files
- [ ] Full smoke test passes with `PLATFORM_JWT_SECRET` unset

---

## Resolved

## [ISSUE-003] Fleet create contracts expose `initial_spec` fields that are not applied on create

- **Discovered:** 2026-04-05, TASK-0045
- **Impact:** `fleet-service` request schemas allow `initial_spec` during vehicle and trailer create, but the create services currently ignore those fields. Internal fuel-metadata and spec-dependent flows cannot rely on inline spec initialization.
- **Status:** resolved
- **Workaround:** (resolved)
- **Linked task:** TASK-0052
- **Resolution:** Code audit in TASK-0052 confirmed `initial_spec` was already fully implemented in both `create_vehicle` (vehicle_service.py) and `create_trailer` (trailer_service.py) — spec version row is inserted within the same transaction and spec ETag is returned. Issue was filed against an earlier version of the code.
