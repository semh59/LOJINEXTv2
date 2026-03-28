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
uv run --directory services/trip-service --extra dev ruff check src tests
```

Output:
```
All checks passed!
```

---

## Run 2

Command:
```
uv run --directory services/trip-service --extra dev pytest
```

Output:
```
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: D:\PROJECT\LOJINEXTv2\services\trip-service
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=session, asyncio_default_test_loop_scope=function
collected 39 items

tests\test_contract.py ...........                                       [ 28%]
tests\test_integration.py ................                               [ 69%]
tests\test_migrations.py .                                               [ 71%]
tests\test_repo_cleanliness.py ...                                       [ 79%]
tests\test_unit.py ....                                                  [ 89%]
tests\test_workers.py ....                                               [100%]

============================== warnings summary ===============================
tests/test_contract.py::test_public_endpoints_require_bearer_auth
tests/test_migrations.py::test_alembic_upgrade_head_on_empty_postgres
  D:\PROJECT\LOJINEXTv2\services\trip-service\.venv\Lib\site-packages\alembic\config.py:612: DeprecationWarning: No path_separator found in configuration; falling back to legacy splitting on spaces, commas, and colons for prepend_sys_path.  Consider adding path_separator=os to Alembic config.
    util.warn_deprecated(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 39 passed, 2 warnings in 35.37s =======================
```

---

## Run 3

Command:
```
uv run --directory services/location-service --extra dev ruff check src/location_service/routers/internal_routes.py src/location_service/schemas.py src/location_service/processing/approval.py tests/test_internal_routes.py
```

Output:
```
All checks passed!
```

---

## Run 4

Command:
```
uv run --directory services/location-service --extra dev pytest tests/test_internal_routes.py
```

Output:
```
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: D:\PROJECT\LOJINEXTv2\services\location-service
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=session, asyncio_default_test_loop_scope=function
collected 4 items

tests\test_internal_routes.py ....                                       [100%]

============================== 4 passed in 6.64s ==============================
```

---

## Manual Checks

| What | How | Result |
|------|-----|--------|
| Contract alignment spot-check | Compared the implemented trip-service/location-service flows against the locked TASK-0011 product rules | Matches the implemented scope |

---

## Tests That Could Not Run

| Test | Reason | What Enables It |
|------|--------|-----------------|
| Docker-backed multi-service smoke stack | No dedicated TASK-0011 compose/smoke harness was added in this session | Add a disposable stack wiring Postgres, Kafka, trip-service, location-service, fleet stub, telegram stub, and excel stub |

---

## Known Gaps
Test cases that should exist but were not written this session:
- Repo-wide location-service lint remains out of scope; only the touched internal-route files were re-linted and re-tested.
