# TEST_EVIDENCE.md

## Status
Final targeted verification completed.

## Evidence

### 1. Trip recovery contract tests

Command:

```powershell
python -m pytest tests/test_contract.py tests/test_integration.py -q
```

Output:

```text
..............................................                           [100%]
============================== warnings summary ===============================
tests/test_contract.py::test_public_endpoints_require_bearer_auth
  C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\alembic\config.py:598: DeprecationWarning: No path_separator found in configuration; falling back to legacy splitting on spaces, commas, and colons for prepend_sys_path.  Consider adding path_separator=os to Alembic config.
    util.warn_deprecated(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
46 passed, 1 warning in 47.06s
```

### 2. Fleet recovery contract + smoke tests

Command:

```powershell
python -m pytest tests/contract/test_internal_contracts.py tests/smoke/test_smoke_probes.py -q
```

Output:

```text
....                                                                     [100%]
============================== warnings summary ===============================
tests/contract/test_internal_contracts.py::test_internal_validate_endpoints
  C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\alembic\config.py:598: DeprecationWarning: No path_separator found in configuration; falling back to legacy splitting on spaces, commas, and colons for prepend_sys_path.  Consider adding path_separator=os to Alembic config.
    util.warn_deprecated(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
4 passed, 1 warning in 13.30s
```

### 3. Driver recovery contract + smoke tests

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_contract.py tests/test_smoke.py -q
```

Output:

```text
........                                                                 [100%]
8 passed in 8.51s
```

## Notes

- During development, earlier failing runs exposed and then drove fixes for:
  - missing `src/` pytest bootstrap in Fleet and Driver service roots
  - Fleet naive/aware UTC mismatches against the current schema
  - Driver smoke/readiness fixture issues caused by shared-session and module-level import behavior
- Driver verification used the repo-local `.venv` because the workstation's global Python interpreter does not currently have `phonenumbers` installed.

## Confidence
High
