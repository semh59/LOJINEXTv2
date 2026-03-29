# TEST_EVIDENCE.md

## Confidence Level
[x] High    — automated tests cover key paths, all pass
[ ] Medium  — some automated + manual, no failures found
[ ] Low     — manual only, or key paths not covered
[ ] None    — could not run — reason below

---

## Run 1

Command:
```
ruff check src tests
```

Output:
```
All checks passed!
```

---

## Run 2

Command:
```
pytest
```

Output:
```
============================= test session starts =============================
platform win32 -- Python 3.14.2, pytest-9.0.1, pluggy-1.6.0
rootdir: D:\PROJECT\LOJINEXTv2\services\location-service
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.12.0, asyncio-1.3.0, cov-7.0.0, respx-0.22.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=session, asyncio_default_test_loop_scope=function
collected 99 items

tests\test_audit_findings.py .............                               [ 13%]
tests\test_auth.py .........                                             [ 22%]
tests\test_config.py .....                                               [ 27%]
tests\test_contract.py ......                                            [ 33%]
tests\test_internal_routes.py .......                                    [ 40%]
tests\test_mock_pipeline.py .                                            [ 41%]
tests\test_pairs_api.py .............                                    [ 54%]
tests\test_points_api.py .......                                         [ 61%]
tests\test_processing_flow.py ..........                                 [ 71%]
tests\test_providers.py ......                                           [ 77%]
tests\test_route_versions_api.py ...                                     [ 80%]
tests\test_schema.py .                                                   [ 81%]
tests\test_schema_integration.py .....                                   [ 86%]
tests\test_unit.py .............                                         [100%]

============================= 99 passed in 45.53s =============================
```

---

## Run 3

Command:
```
TASKS/TASK-0012/scripts/smoke.ps1 -UseLiveProviders
```

Output:
```
Starting docker smoke stack...
Waiting for trip-service /health...
Running alembic migrations inside service containers...


Seeding location-service database for offline smoke...
You are now connected to database "location_service" as user "postgres".
INSERT 0 2
INSERT 0 1
INSERT 0 2
UPDATE 1
INSERT 0 2
Generating JWT tokens in trip-service container...
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

## Run 4

Command:
```
python TASKS/TASK-0022/scripts/location_load.py
```

Output:
```
Load test completed
Elapsed seconds: 349.03
Total requests: 1849
Errors: 0
429 rate: 0.00%
Status counts:
  200: 1759
  201: 30
  202: 60
```

---

## Run 5

Command:
```
docker compose -f TASKS/TASK-0012/docker-compose.smoke.yml down -v --remove-orphans
```

Output:
```
 Container task-0012-trip-service-1 Stopping 
 Container task-0012-telegram-stub-1 Stopping 
 Container task-0012-excel-stub-1 Stopping 
 Container task-0012-telegram-stub-1 Stopped 
 Container task-0012-telegram-stub-1 Removing 
 Container task-0012-telegram-stub-1 Removed 
 Container task-0012-excel-stub-1 Stopped 
 Container task-0012-excel-stub-1 Removing 
 Container task-0012-excel-stub-1 Removed 
 Container task-0012-trip-service-1 Stopped 
 Container task-0012-trip-service-1 Removing 
 Container task-0012-trip-service-1 Removed 
 Container task-0012-fleet-stub-1 Stopping 
 Container task-0012-location-service-1 Stopping 
 Container task-0012-redpanda-1 Stopping 
 Container task-0012-redpanda-1 Stopped 
 Container task-0012-redpanda-1 Removing 
 Container task-0012-redpanda-1 Removed 
 Container task-0012-fleet-stub-1 Stopped 
 Container task-0012-fleet-stub-1 Removing 
 Container task-0012-fleet-stub-1 Removed 
 Container task-0012-location-service-1 Stopped 
 Container task-0012-location-service-1 Removing 
 Container task-0012-location-service-1 Removed 
 Container task-0012-postgres-1 Stopping 
 Container task-0012-postgres-1 Stopped 
 Container task-0012-postgres-1 Removing 
 Container task-0012-postgres-1 Removed 
 Network task-0012_default Removing 
 Network task-0012_default Removed 
```

---

## Manual Checks

| What | How | Result |
|------|-----|--------|
| N/A | N/A | N/A |

---

## Tests That Could Not Run

| Test | Reason | What Enables It |
|------|--------|-----------------|
| N/A | N/A | N/A |

---

## Known Gaps
Test cases that should exist but were not written this session:
- None. All required test matrix items executed.
