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
collected 48 items

tests\test_config.py .....                                               [ 10%]
tests\test_contract.py ...........                                       [ 33%]
tests\test_integration.py ...................                            [ 72%]
tests\test_migrations.py .                                               [ 75%]
tests\test_repo_cleanliness.py ...                                       [ 81%]
tests\test_unit.py ....                                                  [ 89%]
tests\test_workers.py .....                                              [100%]

============================== warnings summary ===============================
tests/test_config.py::test_validate_prod_rejects_default_jwt_secret
tests/test_migrations.py::test_alembic_upgrade_head_on_empty_postgres
  D:\PROJECT\LOJINEXTv2\services\trip-service\.venv\Lib\site-packages\alembic\config.py:612: DeprecationWarning: No path_separator found in configuration; falling back to legacy splitting on spaces, commas, and colons for prepend_sys_path.  Consider adding path_separator=os to Alembic config.
    util.warn_deprecated(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 48 passed, 2 warnings in 37.83s =======================
```
