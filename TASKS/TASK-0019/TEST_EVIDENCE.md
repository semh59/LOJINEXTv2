# TEST_EVIDENCE.md

## Confidence Level
[x] High    - automated tests cover key paths, all pass
[ ] Medium  - some automated + manual, no failures found
[ ] Low     - manual only, or key paths not covered
[ ] None    - could not run - reason below

---

## Run 1

Command:
```
uv run --extra dev ruff check src tests
```

Working Directory:
```
services/location-service
```

Output:
```
All checks passed!
```

---

## Run 2

Command:
```
uv run --extra dev pytest -q
```

Working Directory:
```
services/location-service
```

Output:
```
84 passed in 36.69s
```

---

## Run 3

Command:
```
uv run --extra dev ruff check src tests
```

Working Directory:
```
services/trip-service
```

Output:
```
All checks passed!
```

---

## Run 4

Command:
```
uv run --extra dev pytest -q
```

Working Directory:
```
services/trip-service
```

Output:
```
59 passed, 2 warnings in 56.17s
```

---

## Run 5

Command:
```powershell
uv run --extra dev python -c "import os; from alembic import command; from alembic.config import Config; from testcontainers.postgres import PostgresContainer; container = PostgresContainer('postgres:16-alpine'); container.start();
try:
    url = container.get_connection_url().replace('psycopg2', 'asyncpg')
    os.environ['LOCATION_DATABASE_URL'] = url
    cfg = Config('alembic.ini')
    cfg.set_main_option('sqlalchemy.url', url)
    command.upgrade(cfg, 'head')
    print('ALEMBIC_OK')
finally:
    container.stop()"
```

Working Directory:
```
services/location-service
```

Output:
```
ALEMBIC_OK
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 9f4e4fe14d8c, initial_schema
INFO  [alembic.runtime.migration] Running upgrade 9f4e4fe14d8c -> 0d5f12e97db6, remove_import_export
```

---

## Run 6

Command:
```powershell
./TASKS/TASK-0012/scripts/smoke.ps1 -UseLiveProviders
```

Working Directory:
```
d:\PROJECT\LOJINEXTv2
```

Output excerpt:
```
Offline smoke: manual create trip...
Offline smoke: create empty return...
Offline smoke: Telegram full ingest...
Offline smoke: Telegram fallback ingest...
Offline smoke: Excel ingest...
Offline smoke: driver statement...
Offline smoke: hard delete flow...
Live smoke: creating points and pair in location-service...
Live smoke: validating location internal contracts...
Live smoke: validating trip/location integration...
Smoke completed.
```

---

## Manual Checks

| What | How | Result |
|------|-----|--------|
| Location non-health auth surface | `services/location-service/tests/test_auth.py` and `services/location-service/tests/test_schema_integration.py` | pass |
| Trip/Location business-error mapping | `services/trip-service/tests/test_integration.py` and `services/trip-service/tests/test_workers.py` | pass |
| Live provider calculate -> approve -> resolve -> trip-context -> trip ingest flow | `./TASKS/TASK-0012/scripts/smoke.ps1 -UseLiveProviders` | pass |

---

## Tests That Could Not Run

| Test | Reason | What Enables It |
|------|--------|-----------------|
| - | - | - |

---

## Known Gaps
- TASK-0019 intentionally leaves the persistent processing-worker redesign to `TASKS/TASK-0020/`.
- The smoke script still emits noisy PowerShell `RemoteException` lines because `docker compose exec` writes Alembic INFO logs to stderr; the command exit code is still `0` and the smoke run succeeds.
