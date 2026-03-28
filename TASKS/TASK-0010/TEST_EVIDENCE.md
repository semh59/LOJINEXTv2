# TEST_EVIDENCE.md

## Evidence Log

### 2026-03-27 - Baseline trip-service suite before implementation

Command:

```powershell
uv run --extra dev pytest
```

Output:

```text
31 failed, 17 passed, 1 warning in 32.27s
```

Confidence: None

Notes:
- This run was used to confirm the current failure baseline before implementation.

---

### 2026-03-27 - Final trip-service lint

Command:

```powershell
uv run --extra dev ruff check src tests
```

Output:

```text
All checks passed!
```

Confidence: High

---

### 2026-03-27 - Final trip-service test suite

Command:

```powershell
uv run --extra dev pytest
```

Output:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: D:\PROJECT\LOJINEXTv2\services\trip-service
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=session, asyncio_default_test_loop_scope=function
collected 60 items

tests\test_contract.py ..............                                    [ 23%]
tests\test_integration.py .................                              [ 51%]
tests\test_migrations.py .                                               [ 53%]
tests\test_repo_cleanliness.py ...                                       [ 58%]
tests\test_unit.py .....................                                 [ 93%]
tests\test_workers.py ....                                               [100%]

============================== warnings summary ===============================
tests/test_contract.py::test_error_response_problem_json_format
tests/test_migrations.py::test_alembic_upgrade_head_on_empty_postgres
  D:\PROJECT\LOJINEXTv2\services\trip-service\.venv\Lib\site-packages\alembic\config.py:612: DeprecationWarning: No path_separator found in configuration; falling back to legacy splitting on spaces, commas, and colons for prepend_sys_path.  Consider adding path_separator=os to Alembic config.
    util.warn_deprecated(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 60 passed, 2 warnings in 41.65s =======================
```

Confidence: High

---

### 2026-03-27 - Targeted location-service lint for new internal resolve files

Command:

```powershell
uv run --extra dev ruff check src/location_service/routers/internal_routes.py tests/test_internal_routes.py tests/conftest.py src/location_service/main.py src/location_service/schemas.py src/location_service/errors.py
```

Output:

```text
All checks passed!
```

Confidence: High

Notes:
- A broader `location-service` repo-wide lint run still fails on pre-existing files outside TASK-0010 scope; see `MEMORY/KNOWN_ISSUES.md`.

---

### 2026-03-27 - Targeted location-service internal resolve tests

Command:

```powershell
uv run --extra dev pytest tests/test_internal_routes.py
```

Output:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: D:\PROJECT\LOJINEXTv2\services\location-service
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=session, asyncio_default_test_loop_scope=function
collected 3 items

tests\test_internal_routes.py ...                                        [100%]

============================== 3 passed in 5.81s ==============================
```

Confidence: High

---

### 2026-03-27 - Trip-service Docker image smoke verification

Commands:

```powershell
docker build -t trip-service-prod-smoke .
docker run --rm trip-service-prod-smoke python -c "from trip_service.main import app; print(app.title)"
```

Observed Output:

```text
Trip Service
```

Confidence: Medium

Notes:
- The image built successfully and the container could import `trip_service.main` and print the FastAPI app title.
- A full multi-service Docker smoke stack was not automated in this task.
