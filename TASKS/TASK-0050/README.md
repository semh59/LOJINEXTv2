# TASK-0050 — Identity Service Production Hardening (Retrospective)

## Status: COMPLETED (Remediation Phase)

## Context

Identity service was developed without full alignment to the V2.1 Production Readiness spec. This task tracks the retrospective hardening and remediation of critical security and architectural defects.

## Remediation Log

### 1. SQL Injection Fix

- **Issue:** `admin.py` was using direct f-string interpolation for `ILIKE` queries.
- **Fix:** Implemented parameter binding with wildcard escaping for the `username` filter.

### 2. Admin Router KeyError

- **Issue:** `admin.py` endpoints were accessing `admin["sub"]` which did not exist in the `AuthContext`.
- **Fix:** Corrected to `admin["user_id"]`.

### 3. Role Comparison Standardization

- **Issue:** Used raw string literals for role checks.
- **Fix:** Standardized on `PlatformRole` enum via `platform-auth` package.

### 4. ORM Model Hardening

- **Issue:** Missing `__table_args__` and production indexes.
- **Fix:** Added comprehensive indexes for Audit Log, Outbox, and Refresh Tokens.

### 5. Outbox Model Alignment

- **Issue:** Missing `published_at_utc` column (caused relay worker drift).
- **Fix:** Added `published_at_utc` to `IdentityOutboxModel`.

### 6. Production Security

- **Issue:** OpenAPI docs exposed in all environments.
- **Fix:** Conditional disabling of `docs_url` and `redoc_url` based on `IDENTITY_ENVIRONMENT`.

## Verification

- Verified via import smoke test.
- Full test suite passes (test_auth, test_config, test_migrations, test_security_boundary, test_stress, test_workers).
