# Location-Service Production Readiness Audit

**Date:** 2026-04-07  
**Scope:** Deep inspection — contracts, API, endpoints, database, frontend plan, inter-service communication, code & algorithms  
**Verdict:** ⚠️ NEAR PRODUCTION — 4 blockers must be resolved before go-live

---

## Context

This document is a full production-readiness audit of `services/location-service`. The service is the geographic route authority for LOJINEXTv2. It owns all `LocationPoint`, `RoutePair`, `Route`, `RouteVersion`, `RouteSegment`, and `ProcessingRun` data. Trip-service is its primary consumer via internal HTTP. It publishes domain events to Kafka via the transactional outbox pattern.

---

## 1. Architecture Overview

```
[Frontend / Admin UI]
        │ HTTP (user JWT)
        ▼
[location-service :8103]
   ├── Points API         /v1/points
   ├── Pairs API          /v1/pairs
   ├── Processing API     /v1/pairs/{id}/calculate|refresh
   ├── Approval API       /v1/pairs/{id}/approve|discard
   ├── Bulk Refresh API   /v1/bulk-refresh/jobs
   ├── Routes API         /v1/routes/{id}/versions/{no}
   ├── Internal API       /internal/v1/routes/resolve
   │                      /internal/v1/route-pairs/{id}/trip-context
   ├── Health             /health  /ready  /metrics
   │
   ├── [Processing Worker]  → claims ProcessingRun rows (SKIP_LOCKED)
   │        └── calls Mapbox Directions API (primary)
   │        └── calls ORS Validation API (optional validator)
   │        └── calls Mapbox Terrain API (elevation)
   │
   └── [Outbox Relay Worker] → publishes to Kafka topic: location-events
              └── V2.1 pattern: SKIP_LOCKED, per-event commit, stale claim recovery

[trip-service :8101]
   └── POST /internal/v1/routes/resolve        (Bearer: trip-service token)
   └── GET  /internal/v1/route-pairs/{id}/trip-context
```

---

## 2. Database Schema Status

### Tables (14 total, 7 migrations complete)

| Table | PK | Notable Constraints |
|---|---|---|
| `location_points` | ULID | Unique: code, (lat,lng), norm_name_tr, norm_name_en; CHECK lat/lng bounds |
| `route_pairs` | ULID | Unique: pair_code; Partial unique index: (origin,dest,profile) WHERE status IN (ACTIVE,DRAFT) |
| `routes` | ULID | Unique: route_code |
| `route_version_counters` | route_id (FK) | Sequence counter per route |
| `route_versions` | (route_id, version_no) | Partial unique index: route_id WHERE status=ACTIVE |
| `route_segments` | (route_id, version_no, seg_no) | CHECK seg_no>=1, distances>=0 |
| `processing_runs` | ULID | Partial unique: route_pair_id WHERE status IN (QUEUED,RUNNING); claim columns |
| `bulk_refresh_jobs` | ULID | JSONB selection_scope |
| `bulk_refresh_job_items` | ULID | Unique: (job_id, item_no); FK CASCADE delete |
| `route_usage_refs` | (route_id, version_no, svc, type, entity) | FK RESTRICT on delete |
| `idempotency_keys` | key_hash(64) | expires_at_utc for TTL cleanup |
| `worker_heartbeats` | worker_name(100) | Simple timestamp registry |
| `location_outbox` | ULID | V2.1: claim_expires_at_utc, last_error_code, retry_count |
| `location_audit_log` | ULID | Immutable; indexes: (target_type, target_id, created_at_utc) |

### Migration Chain (clean, no gaps)
```
9f4e4fe14d8c → 0d5f12e97db6 → 4d2b8c9e7f10 → 7b1e9b8b2c6a → e5f6a1b2c3d4 → f1a2b3c4d5e6 → 1a2b3c4d5e6f
```
All models match final migration state. ✅

---

## 3. API Endpoints (Full Inventory)

### Public (user JWT)
| Method | Path | Status Code | Description |
|---|---|---|---|
| POST | `/v1/points` | 201 | Create location point |
| GET  | `/v1/points` | 200 | List points (paginated, search, sort) |
| GET  | `/v1/points/{id}` | 200 | Get single point |
| PATCH | `/v1/points/{id}` | 200 | Update name/active status |
| POST | `/v1/pairs` | 201 | Create route pair |
| GET  | `/v1/pairs` | 200 | List pairs |
| GET  | `/v1/pairs/{id}` | 200 | Get pair |
| PATCH | `/v1/pairs/{id}` | 200 | Update profile_code |
| DELETE | `/v1/pairs/{id}` | 204 | Soft delete pair |
| POST | `/v1/pairs/{id}/calculate` | 202 | Enqueue processing run |
| POST | `/v1/pairs/{id}/refresh` | 202 | Enqueue refresh run |
| GET  | `/v1/pairs/{id}/processing-runs` | 200 | List runs for pair |
| GET  | `/v1/processing-runs/{id}` | 200 | Get single run |
| GET  | `/v1/routes/{id}/versions/{no}` | 200 | Route version detail |
| GET  | `/v1/routes/{id}/versions/{no}/geometry` | 200 | Segment geometry |

### Super-Admin Only
| Method | Path | Status Code | Description |
|---|---|---|---|
| POST | `/v1/pairs/{id}/approve` | 200 | Promote DRAFT → ACTIVE |
| POST | `/v1/pairs/{id}/discard` | 200 | Discard pending draft |
| POST | `/v1/processing-runs/{id}/force-fail` | 200 | Force-fail stuck run |
| POST | `/v1/bulk-refresh/jobs` | 202 | Bulk refresh trigger |

### Internal (trip-service token only)
| Method | Path | Description |
|---|---|---|
| POST | `/internal/v1/routes/resolve` | Resolve route pair by origin/destination name |
| GET  | `/internal/v1/route-pairs/{id}/trip-context` | Get durations + route IDs for a pair |

### Infrastructure
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness (DB + broker + Mapbox + ORS + worker heartbeat) |
| GET | `/metrics` | Prometheus |

---

## 4. Kafka Events Published

Topic: `location-events` (outbox pattern, V2.1)

| Event Name | Trigger | Key Payload Fields |
|---|---|---|
| `location.point.created.v1` | POST /v1/points | location_id, code |
| `location.point.updated.v1` | PATCH /v1/points/{id} | location_id |
| `location.pair.created.v1` | POST /v1/pairs | pair_id, pair_code |
| `location.pair.updated.v1` | PATCH /v1/pairs/{id} | pair_id |
| `location.pair.soft_deleted.v1` | DELETE /v1/pairs/{id} | pair_id |
| `location.route.activated.v1` | POST /v1/pairs/{id}/approve | pair_id, forward_route_id, reverse_route_id |
| `location.route.discarded.v1` | POST /v1/pairs/{id}/discard | pair_id |

All events wrapped in envelope: `{event_id, event_name, event_version, aggregate_id, aggregate_type, payload, published_at_utc}`

---

## 5. Inter-Service Communication

### Inbound (location-service receives)
- **trip-service** → `POST /internal/v1/routes/resolve` + `GET /internal/v1/route-pairs/{id}/trip-context`
  - Auth: Bearer token (service account `trip-service`, role `SERVICE`)
  - Source: `services/trip-service/src/trip_service/dependencies.py:244,282`
  - Also called from enrichment worker: `services/trip-service/src/trip_service/workers/enrichment_worker.py:158`

### Outbound (location-service calls)
- **Mapbox Directions v5** — route geometry + distance/duration (primary provider)
- **Mapbox Terrain v4** — elevation raster tiles per segment
- **ORS (OpenRouteService)** — optional distance/duration delta validation
- **No calls to other LOJINEXTv2 services** ✅

### Service Discovery
- `TRIP_LOCATION_SERVICE_URL=http://location-api:8103` (compose)
- `LOCATION_AUTH_JWT_*` settings issued by identity-service

---

## 6. Processing Pipeline (Algorithm)

```
User POST /calculate
  │
  ▼
Create ProcessingRun (QUEUED) + write to outbox
  │
  ▼ [Processing Worker — separate process]
Claim run (FOR UPDATE SKIP LOCKED, claim_token, claim_expires_at 300s)
  │
  ├── Call Mapbox Directions → geometry + distance_m + duration_s
  │     └── If fail: mark run FAILED (attempt_no++)
  │
  ├── Call Mapbox Terrain → elevation per segment
  │
  ├── (If ORS enabled) Call ORS Validate
  │     └── Compare distance/duration delta vs SLA thresholds
  │         distance: FAIL > 15%, WARN > 5%
  │         duration: FAIL > 20%, WARN > 10%
  │
  ├── Compute: ascent/descent, grade stats, road/speed/urban distributions
  │
  ├── Create RouteVersion (CALCULATED_DRAFT) + RouteSegments
  │     └── version_no from RouteVersionCounter (atomic increment)
  │
  └── Mark ProcessingRun SUCCEEDED
        └── Update RoutePair.pending_forward/reverse_version_no

User POST /approve
  └── Promote CALCULATED_DRAFT → ACTIVE
  └── Mark prior ACTIVE version → SUPERSEDED
  └── Write location.route.activated.v1 to outbox
```

---

## 7. Test Coverage Assessment

| Area | Files | Tests | Status |
|---|---|---|---|
| Points CRUD | test_points_api.py | 11 | ✅ |
| Pairs CRUD | test_pairs_api.py | 16 | ✅ |
| Processing flow | test_processing_flow.py | 15 | ✅ |
| Internal routes | test_internal_routes.py | 7 | ✅ |
| Audit log | test_audit_findings.py | 13 | ✅ |
| Outbox relay | test_outbox_deep.py | 4 | ⚠️ partial |
| Providers | test_providers.py | 7 | ✅ |
| Auth | test_auth.py | ~6 | ✅ |
| Config | test_config.py | ~6 | ✅ |
| Migrations | test_migrations.py | 3 | ✅ |
| Contract (Pact) | — | **0** | ❌ MISSING |
| Worker heartbeat | — | **0** | ❌ MISSING |
| Outbox event schema | — | **0** | ❌ MISSING |
| Provider probe cache | — | **0** | ❌ MISSING |

**Total: ~122 tests** across 18 files.

---

## 8. Issues Found — By Severity

### 🔴 BLOCKER (must fix before prod)

**B-1: No Pact contract tests for trip-service ↔ location-service internal routes**
- Trip-service calls `/internal/v1/routes/resolve` and `/internal/v1/route-pairs/{id}/trip-context`
- No Pact consumer/provider verification exists
- A schema change in either service can silently break the integration
- Fix: Add Pact consumer tests in trip-service, provider verification in location-service tests
- Files: `services/trip-service/src/trip_service/dependencies.py:244,282`, `services/location-service/src/location_service/routers/internal_routes.py`

**B-2: Auth uses string literals instead of PlatformRole enum (PLATFORM_STANDARD binding violation)**
- File: `services/location-service/src/location_service/auth.py`
- Issue: Role comparisons done with bare strings ("SUPER_ADMIN", "ADMIN", etc.)
- PLATFORM_STANDARD §5.3 explicitly lists this as a violation
- Fix: Import and use `PlatformRole` enum from `platform-auth` package

**B-3: Missing indexes on ORM models (ORM ↔ migration drift)**
- `location_outbox` and `location_audit_log` have indexes in migrations but NOT in ORM `__table_args__`
- Migrations: `f1a2b3c4d5e6` creates `idx_location_outbox_pending` and `idx_location_audit_target`
- ORM: `models.py:395-429` has no `__table_args__` with Index definitions
- Risk: Schema introspection tools (alembic autogenerate, sqlacodegen) will report drift and may generate wrong migrations
- Fix: Add `__table_args__` with matching Index definitions to both ORM models

**B-4: Missing index on ProcessingRun.route_pair_id**
- FK exists but no explicit index
- List-by-pair queries (`GET /v1/pairs/{id}/processing-runs`) do full table scans under load
- File: `services/location-service/src/location_service/models.py:247-289`
- Fix: Add `Index("idx_processing_runs_pair_id", "route_pair_id")` in `__table_args__` + migration

---

### 🟡 IMPORTANT (fix before scale)

**I-1: partition_key not indexed on location_outbox**
- Outbox relay worker groups by partition_key for Kafka routing
- Queries on partition_key will be sequential scans
- File: `services/location-service/src/location_service/models.py:404`
- Fix: Add index on `partition_key`

**I-2: claim_expires_at_utc not indexed on location_outbox**
- Outbox relay reclaim queries (find expired PUBLISHING rows) are unindexed
- Added by migration `1a2b3c4d5e6f` but no index created
- Fix: Add index on `claim_expires_at_utc` WHERE `publish_status = 'PUBLISHING'`

**I-3: No worker heartbeat tests**
- `worker_heartbeats.py` has `record_worker_heartbeat()` and `read_worker_heartbeat()` but zero tests
- Readiness probe depends on heartbeat staleness detection (60s threshold)
- Risk: Silent breakage of worker liveness detection
- Fix: Add tests for write, staleness timeout, recovery

**I-4: No outbox event schema validation tests**
- `payload_json` in outbox is JSONB with no DB-level schema
- event_name patterns, aggregate_type enum values, and payload structure are unverified in tests
- Fix: Add schema assertion tests in `test_outbox_deep.py`

**I-5: RouteSegment.segment_no sequential continuity not validated**
- DB allows gaps (e.g., segments 1, 3, 5) — no contiguity check
- Geometry reconstruction in `routes_public.py` assumes ordered sequential segments
- Fix: Add CHECK constraint or application-level validation in the processing pipeline

---

### 🔵 LOW (tech debt, won't block go-live)

**L-1: speed_band String(50) has no DB CHECK constraint**
- Enum values enforced in Python code only
- Stale/invalid values can be inserted directly via SQL
- File: `services/location-service/src/location_service/models.py:227`

**L-2: ProcessingRun.error_message is String(1024)**
- Provider stack traces can exceed 1KB and will be silently truncated
- Consider `Text` type or dedicated error detail table

**L-3: JSONB field structures (distributions, field_origin_matrix_json) not validated at DB layer**
- Application must enforce structure — no DB-level guard
- Risk: Silent payload corruption from incorrect clients

**L-4: LocationPoint.is_active changes not always captured in audit log**
- Audit log records point mutations, but deactivation via PATCH may not always emit audit if skipped upstream
- Low risk — audit_helpers.py should cover it, but explicit test missing

---

## 9. Frontend Plan Status

Per `MEMORY/DECISIONS.md`, **TASK-0021** covers "Frontend public contract work" and is currently **DEFERRED**.

Current public API is suitable for internal admin UI (user JWT endpoints are complete). Before a public-facing frontend can consume this service:

1. OpenAPI spec must be published and versioned (currently disabled in prod via `docs_url=None`)
2. Pagination is offset-based (`page` + `per_page`) — adequate for admin but not infinite scroll
3. The `GET /v1/routes/{id}/versions/{no}/geometry` endpoint returns raw `[lng, lat][]` — GeoJSON wrapper would be cleaner for map libraries
4. No rate limiting is configured for external consumers
5. CORS policy not defined in middleware

---

## 10. Production Readiness Checklist

| Category | Status | Notes |
|---|---|---|
| Database schema & migrations | ✅ | 7 clean migrations, final state matches ORM |
| API endpoint coverage | ✅ | 20+ endpoints, all async |
| Auth (RS256, JWKS, prod guard) | ✅ | Platform-auth used; prod validation enforced |
| Auth role enum compliance | ❌ B-2 | String literals instead of PlatformRole |
| Error format (RFC 9457) | ✅ | Problem+JSON, 30+ named errors |
| Service boundary compliance | ✅ | No cross-DB, no cross-import violations |
| Outbox V2.1 | ✅ | SKIP_LOCKED, per-event commit, stale recovery |
| Kafka events schema | ✅ | 7 event types, envelope structure correct |
| Processing worker (distributed) | ✅ | Claim token, heartbeat, retry logic |
| Readiness probe (real checks) | ✅ | DB + broker + Mapbox + ORS + worker heartbeat |
| Prometheus metrics | ✅ | PrometheusMiddleware + worker counters |
| Audit log | ✅ | All mutations logged with snapshots |
| Idempotency keys | ✅ | 24hr TTL |
| Contract tests (Pact) | ❌ B-1 | Not implemented |
| ORM ↔ migration index drift | ❌ B-3 | Indexes missing from ORM models |
| ProcessingRun FK index | ❌ B-4 | Missing index on route_pair_id |
| Worker heartbeat tests | ❌ I-3 | No test coverage |
| Outbox event schema tests | ❌ I-4 | No test coverage |
| Frontend contract (TASK-0021) | ⏸ | Deferred per DECISIONS.md |

---

## 11. Recommended Fix Order

### Phase 1 — Blockers (1–2 days)
1. **B-2**: Refactor `auth.py` to use `PlatformRole` enum
2. **B-3**: Add `__table_args__` Index definitions to `LocationOutboxModel` and `LocationAuditLogModel` in `models.py`
3. **B-4**: Add migration + ORM index for `ProcessingRun.route_pair_id`
4. **B-1**: Add Pact-style contract tests for trip→location internal routes (can use respx mocks as minimum viable contracts)

### Phase 2 — Important (3–5 days)
5. **I-1 + I-2**: Add outbox index migrations for `partition_key` and `claim_expires_at_utc`
6. **I-3**: Add worker heartbeat tests to test suite
7. **I-4**: Add outbox event schema assertion tests
8. **I-5**: Add segment_no contiguity validation in processing pipeline

### Phase 3 — Frontend TASK-0021 (when prioritized)
9. Enable OpenAPI docs behind feature flag
10. Add GeoJSON wrapper to geometry endpoint
11. Define CORS + rate limiting policy

---

## Critical Files

| File | Role |
|---|---|
| `services/location-service/src/location_service/models.py` | ORM models (14 tables) — B-3, B-4, I-1, I-2 fixes here |
| `services/location-service/src/location_service/auth.py` | Role enum fix (B-2) |
| `services/location-service/src/location_service/routers/internal_routes.py` | Contract surface for trip-service (B-1) |
| `services/location-service/src/location_service/workers/outbox_relay.py` | Outbox relay logic |
| `services/location-service/src/location_service/worker_heartbeats.py` | Heartbeat logic needing test (I-3) |
| `services/location-service/tests/test_outbox_deep.py` | Extend for schema assertions (I-4) |
| `services/location-service/alembic/versions/` | New migration needed for B-4, I-1, I-2 |
| `services/trip-service/src/trip_service/dependencies.py:244,282` | Trip-service consumer of internal routes |
