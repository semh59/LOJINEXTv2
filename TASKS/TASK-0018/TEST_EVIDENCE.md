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
uv run ruff check src tests
```

Output:
```
All checks passed!
```

---

## Run 2

Command:
```
uv run pytest
```

Output:
```
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: D:\PROJECT\LOJINEXTv2\services\location-service
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=session, asyncio_default_test_loop_scope=function
collected 63 items

tests\test_audit_findings.py .............                               [ 20%]
tests\test_internal_routes.py ......                                     [ 30%]
tests\test_mock_pipeline.py .                                            [ 31%]
tests\test_pairs_api.py ........                                         [ 44%]
tests\test_points_api.py ......                                          [ 53%]
tests\test_processing_flow.py ........                                   [ 66%]
tests\test_providers.py ....                                             [ 73%]
tests\test_schema.py .                                                   [ 74%]
tests\test_schema_integration.py ...                                     [ 79%]
tests\test_unit.py .............                                         [100%]

============================= 63 passed in 24.81s =============================
```

---

## Run 3

Command:
```
uv run python - <<'PY'
from testcontainers.postgres import PostgresContainer
# starts disposable PostgreSQL, runs `uv run alembic upgrade head`,
# then verifies import/export tables and `processing_runs.import_job_id` are absent
PY
```

Output:
```
alembic upgrade head verified against disposable PostgreSQL
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 9f4e4fe14d8c, initial_schema
INFO  [alembic.runtime.migration] Running upgrade 9f4e4fe14d8c -> 0d5f12e97db6, remove_import_export
```

---

## Manual Checks

| What | How | Result |
|------|-----|--------|
| Import/export routes removed from public surface | `tests/test_audit_findings.py` checks `/openapi.json`, `POST /v1/import`, and `GET /v1/export` | pass |
| ACTIVE-version-only internal resolve | `tests/test_internal_routes.py` covers active-pointer filtering and ambiguity | pass |
| Pair `row_version` mutation paths | `tests/test_pairs_api.py` and `tests/test_processing_flow.py` assert row_version changes on patch/approval/discard/pipeline | pass |

---

## Tests That Could Not Run

| Test | Reason | What Enables It |
|------|--------|-----------------|
| - | - | - |

---

## Known Gaps
- Background processing still uses mocked provider clients in unit tests; TASK-0018 did not add full end-to-end external provider integration coverage.
- Migration verification proves schema cleanup on disposable PostgreSQL, but not data migration of any historical import/export rows because that work is explicitly out of scope.
