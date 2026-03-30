You are picking up a completed task.
Read this before changing anything related to TASK-0033.

---

## Task Status
- TASK-0033 is complete for its planned scope.
- Both targeted pytest suites passed.

---

## What Was Built
- Trip Service:
  - Added `TripOutbox.last_error_code` ORM parity.
  - Refactored outbox relay to claim in batch and finalize each event in its own transaction.
  - Added advisory transaction locks for overlap checks.
  - Hid `SOFT_DELETED` trips by default in `GET /api/v1/trips`.
  - Enforced `If-Match` before idempotent cancel early return.
  - Persisted `source_payload_hash` for manual and empty-return creates.
  - Reset enrichment attempt count on every manual retry.
  - Reused shared HTTP clients and closed them on shutdown.
  - Softened worker/cleanup behavior when schema is not migrated yet.
- Location Service:
  - Replaced the active-only pair uniqueness index with a live-pair (`ACTIVE`/`DRAFT`) uniqueness index via Alembic.
  - Mapped live-pair uniqueness integrity failures to `409`.
  - Hid `SOFT_DELETED` pairs by default; `is_active=false` now means `DRAFT`.
  - Added `LOCATION_INVALID_FILTER_COMBINATION`.
  - Added cached provider probes and readiness live-status gating.
  - Persisted validation deltas and segment metadata from Mapbox step intersections.
  - Added regression coverage for migration guardrails, readiness, normalization, and pair semantics.

---

## Important Follow-Up Context
- `services/location-service/alembic/env.py` uses `settings.database_url` during migration runs. Tests had to set both `settings.database_url` and Alembic config URL when targeting temporary databases.
- Outbox delivery is still at-least-once. TASK-0033 reduced the transaction blast radius; it did not change downstream deduplication expectations.

---

## If You Need To Extend This Area
1. Re-run:
   - `uv run pytest tests/test_workers.py tests/test_integration.py tests/test_migrations.py -q` in `services/trip-service`
   - `uv run pytest tests/test_pairs_api.py tests/test_processing_flow.py tests/test_mock_pipeline.py tests/test_providers.py tests/test_schema_integration.py tests/test_unit.py tests/test_migrations.py -q` in `services/location-service`
2. Keep `TASKS/TASK-0033/TEST_EVIDENCE.md` aligned with any new verification.
3. If you touch Location migrations or their tests, remember the `settings.database_url` requirement above.

---

## Temporary Implementations

| What | Where | Permanent Solution | Task |
|------|-------|--------------------|------|
| None | - | - | - |
