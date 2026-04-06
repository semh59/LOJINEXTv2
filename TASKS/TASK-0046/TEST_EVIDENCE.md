# TEST_EVIDENCE.md

## Confidence Level
[x] High    - automated tests cover key paths, all pass
[ ] Medium  - some automated + manual, no failures found
[ ] Low     - manual only, or key paths not covered
[ ] None    - could not run - reason below

Reason:
- Deep local validation is green and the module coverage targets from the test plan are met.
- The only remaining blocker is the configured target DB backfill gate, which is still blocked by an unreachable database.

---

## Run 1

Command:
```powershell
uv sync --extra dev
```

Output:
```text
Resolved 61 packages in 4ms
Audited 60 packages in 6ms
```

---

## Run 2

Command:
```powershell
uv run ruff check src tests
```

Output:
```text
All checks passed!
```

---

## Run 3

Command:
```powershell
uv run pytest -q tests/test_auth_deep.py tests/test_dependencies_deep.py tests/test_http_clients_deep.py tests/test_timezones_deep.py tests/test_broker_deep.py tests/test_entrypoints_deep.py tests/test_observability_deep.py
```

Output:
```text
...........................................................              [100%]
============================== warnings summary ===============================
tests/test_auth_deep.py::test_auth_verify_status_rejects_invalid_local_settings[settings_obj0-fail]
  D:\PROJECT\LOJINEXTv2\services\trip-service\.venv\Lib\site-packages\alembic\config.py:612: DeprecationWarning: No path_separator found in configuration; falling back to legacy splitting on spaces, commas, and colons for prepend_sys_path.  Consider adding path_separator=os to Alembic config.
    util.warn_deprecated(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
59 passed, 1 warning in 35.70s
```

---

## Run 4

Command:
```powershell
uv run pytest -q tests/test_unit.py tests/test_config.py tests/test_contract.py tests/test_runtime.py tests/test_integration.py tests/test_workers.py tests/test_reliability_deep.py tests/test_backfill_status_drift.py tests/test_migrations.py
```

Output:
```text
........................................................................ [ 60%]
...............................................                          [100%]
============================== warnings summary ===============================
tests/test_unit.py::test_latest_evidence_prefers_newest_created_at
tests/test_migrations.py::test_alembic_upgrade_head_on_empty_postgres
  D:\PROJECT\LOJINEXTv2\services\trip-service\.venv\Lib\site-packages\alembic\config.py:612: DeprecationWarning: No path_separator found in configuration; falling back to legacy splitting on spaces, commas, and colons for prepend_sys_path.  Consider adding path_separator=os to Alembic config.
    util.warn_deprecated(

tests/test_integration.py::test_validate_trip_references_sends_fleet_auth_and_accepts_compat_response
  D:\PROJECT\LOJINEXTv2\services\trip-service\.venv\Lib\site-packages\jwt\api_jwt.py:147: InsecureKeyLengthWarning: The HMAC key is 24 bytes long, which is below the minimum recommended length of 32 bytes for SHA256. See RFC 7518 Section 3.2.
    return self._jws.encode(

tests/test_integration.py::test_validate_trip_references_sends_fleet_auth_and_accepts_compat_response
  D:\PROJECT\LOJINEXTv2\services\trip-service\.venv\Lib\site-packages\jwt\api_jwt.py:365: InsecureKeyLengthWarning: The HMAC key is 24 bytes long, which is below the minimum recommended length of 32 bytes for SHA256. See RFC 7518 Section 3.2.
    decoded = self.decode_complete(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
119 passed, 4 warnings in 107.61s (0:01:47)
```

---

## Run 5

Command:
```powershell
uv run pytest --cov=src/trip_service --cov-report=term-missing:skip-covered --cov-fail-under=85 -q
```

Output:
```text
........................................................................ [ 35%]
........................................................................ [ 71%]
.........................................................                [100%]
=============================== tests coverage ================================
Required test coverage of 85% reached. Total coverage: 91.73%
201 passed, 4 warnings in 155.23s (0:02:35)

Module targets reached:
- `auth.py` -> 98%
- `dependencies.py` -> 91%
- `http_clients.py` -> 100%
- `timezones.py` -> 94%
- `routers/health.py` -> 96%
- `broker.py` -> 89%
- `observability.py` -> 98%
- `workers/enrichment_worker.py` -> 91%
- `workers/outbox_relay.py` -> 93%
- `routers/trips.py` -> 85%
```

---

## Run 6

Command:
```powershell
uv run python -c "from trip_service.main import app; print(sorted((route.path, sorted(route.methods or [])) for route in app.routes))"
```

Output:
```text
[('/api/v1/trips', ['GET']), ('/api/v1/trips', ['POST']), ('/api/v1/trips/export-jobs', ['POST']), ('/api/v1/trips/export-jobs/{job_id}', ['GET']), ('/api/v1/trips/export-jobs/{job_id}/download', ['GET']), ('/api/v1/trips/import-files', ['POST']), ('/api/v1/trips/import-jobs', ['POST']), ('/api/v1/trips/import-jobs/{job_id}', ['GET']), ('/api/v1/trips/{base_trip_id}/empty-return', ['POST']), ('/api/v1/trips/{trip_id}', ['GET']), ('/api/v1/trips/{trip_id}', ['PATCH']), ('/api/v1/trips/{trip_id}/approve', ['POST']), ('/api/v1/trips/{trip_id}/cancel', ['POST']), ('/api/v1/trips/{trip_id}/hard', ['DELETE']), ('/api/v1/trips/{trip_id}/hard-delete', ['POST']), ('/api/v1/trips/{trip_id}/reject', ['POST']), ('/api/v1/trips/{trip_id}/retry-enrichment', ['POST']), ('/api/v1/trips/{trip_id}/timeline', ['GET']), ('/docs', ['GET', 'HEAD']), ('/docs/oauth2-redirect', ['GET', 'HEAD']), ('/health', ['GET']), ('/internal/v1/assets/reference-check', ['POST']), ('/internal/v1/driver/trips', ['GET']), ('/internal/v1/trips/driver-check/{driver_id}', ['GET']), ('/internal/v1/trips/excel/export-feed', ['GET']), ('/internal/v1/trips/excel/ingest', ['POST']), ('/internal/v1/trips/slips/ingest', ['POST']), ('/internal/v1/trips/slips/ingest-fallback', ['POST']), ('/metrics', ['GET']), ('/openapi.json', ['GET', 'HEAD']), ('/ready', ['GET']), ('/redoc', ['GET', 'HEAD'])]
```

---

## Run 7

Command:
```powershell
uv run python scripts/backfill_trip_status_drift.py --dry-run
```

Output:
```text
ConnectionRefusedError: [WinError 1225] Uzaktaki bilgisayar ağ bağlantısını reddetti
```

---

## Run 8

Command:
```powershell
@'
import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from scripts.backfill_trip_status_drift import run_backfill

service_root = Path.cwd()
alembic_cfg = Config(str(service_root / 'alembic.ini'))
alembic_cfg.set_main_option('script_location', str(service_root / 'alembic'))
alembic_cfg.set_main_option('prepend_sys_path', str(service_root / 'src'))

async def run_check(url: str) -> None:
    engine = create_async_engine(url)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        summary = await run_backfill(apply=False, session_factory=session_factory)
        print({
            'blocking_rows': [row.id for row in summary.blocking_rows],
            'applied_counts': summary.applied_counts,
            'remaining_counts': summary.remaining_counts,
            'exit_code': 0 if not summary.blocking_rows and not summary.remaining_counts else 1,
        })
    finally:
        await engine.dispose()

with PostgresContainer('postgres:16-alpine') as pg:
    url = pg.get_connection_url().replace('postgresql+psycopg2://', 'postgresql+asyncpg://')
    url = url.replace('postgresql://', 'postgresql+asyncpg://')
    alembic_cfg.set_main_option('sqlalchemy.url', url)
    command.upgrade(alembic_cfg, 'head')
    asyncio.run(run_check(url))
'@ | uv run python -
```

Output:
```text
{'blocking_rows': [], 'applied_counts': {'CANCELLED': 0, 'ASSIGNED': 0}, 'remaining_counts': {}, 'exit_code': 0}
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> a1b2c3d4e5f6, trip_service_baseline
INFO  [alembic.runtime.migration] Running upgrade a1b2c3d4e5f6 -> b2c3d4e5f6a1, add outbox claims
INFO  [alembic.runtime.migration] Running upgrade b2c3d4e5f6a1 -> c1d2e3f4a5b6, add worker heartbeats
INFO  [alembic.runtime.migration] Running upgrade c1d2e3f4a5b6 -> d1e2f3a4b5c6, add trip audit log table
```

---

## Manual Checks

| What | How | Result |
|------|-----|--------|
| Deep branch tests stay green after source fixes | Focused `pytest` gates for auth, dependencies, broker, entrypoints, observability, workers, integration, and backfill. | Pass |
| Phase A route surface still loads | Imported `trip_service.main` and printed the registered route paths plus allowed methods. | Pass |
| Backfill gate is environmental, not repo-only | Ran the same `--dry-run` flow against an ephemeral migrated Postgres instance. | Pass |

---

## Tests That Could Not Run

| Test | Reason | What Enables It |
|------|--------|-----------------|
| `uv run python scripts/backfill_trip_status_drift.py --apply` against the configured DB | The configured DB rejects connections at `127.0.0.1:5433`. | Restore connectivity to the real `trip-service` database. |
| Verification `uv run python scripts/backfill_trip_status_drift.py --dry-run` after real `--apply` | `--apply` could not run against the configured DB. | Complete a clean real-DB `--apply` first. |

---

## Known Gaps
- Phase B strict cleanup was intentionally not started because the real DB gate is still blocked.
- The route smoke output still contains the legacy `/api/v1/trips/{trip_id}/hard` alias; this task records that fact but does not change it.
- Warnings remain from Alembic config deprecation and intentionally short HS test secret usage; these are test-environment warnings, not failing assertions.
