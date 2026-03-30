# TEST_EVIDENCE.md

## Confidence Level
[x] High    - automated tests cover key paths, all pass
[ ] Medium  - some automated + manual, no failures found
[ ] Low     - manual only, or key paths not covered
[ ] None    - could not run - reason below

---

## Run 1

Command:
```powershell
uv run pytest tests/test_workers.py tests/test_integration.py tests/test_migrations.py -q
```

Output:
```text
........................................                                 [100%]
============================== warnings summary ===============================
tests/test_workers.py::test_outbox_first_failure_backoff_is_five_seconds
tests/test_migrations.py::test_alembic_upgrade_head_on_empty_postgres
  D:\PROJECT\LOJINEXTv2\services\trip-service\.venv\Lib\site-packages\alembic\config.py:612: DeprecationWarning: No path_separator found in configuration; falling back to legacy splitting on spaces, commas, and colons for prepend_sys_path.  Consider adding path_separator=os to Alembic config.
    util.warn_deprecated(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
40 passed, 2 warnings in 54.84s
```

---

## Run 2

Command:
```powershell
uv run pytest tests/test_pairs_api.py tests/test_processing_flow.py tests/test_mock_pipeline.py tests/test_providers.py tests/test_schema_integration.py tests/test_unit.py tests/test_migrations.py -q
```

Output:
```text
........................................................                 [100%]
============================== warnings summary ===============================
tests/test_migrations.py::test_alembic_upgrade_head_creates_live_pair_unique_index
tests/test_migrations.py::test_alembic_live_pair_uniqueness_migration_blocks_duplicate_drafts
tests/test_migrations.py::test_alembic_live_pair_uniqueness_migration_blocks_duplicate_drafts
  D:\PROJECT\LOJINEXTv2\services\location-service\.venv\Lib\site-packages\alembic\config.py:612: DeprecationWarning: No path_separator found in configuration; falling back to legacy splitting on spaces, commas, and colons for prepend_sys_path.  Consider adding path_separator=os to Alembic config.
    util.warn_deprecated(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
56 passed, 3 warnings in 44.02s
```

---

## Manual Checks

| What | How | Result |
|------|-----|--------|
| Trip and Location task records | Updated after implementation and test runs | pass |
| Syntax sanity | `py_compile` on changed Trip and Location modules/tests before pytest | pass |

---

## Tests That Could Not Run

| Test | Reason | What Enables It |
|------|--------|-----------------|
| None | - | - |

---

## Known Gaps
- Targeted suites cover the new behavior, but there is no dedicated unit test for the worker/cleanup schema-not-ready warning branches; those paths remain indirectly validated by implementation review rather than direct assertion.
