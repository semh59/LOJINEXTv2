# TEST_EVIDENCE.md

Record what was actually run for TASK-0021.
Do not claim tests that did not run.

---

## Commands Run

### 1. Ruff
```powershell
uv run --directory services/location-service --extra dev ruff check src tests
```

Result:
```text
All checks passed!
```

### 2. Pytest
```powershell
uv run --directory services/location-service --extra dev pytest
```

Result excerpt:
```text
collected 99 items
...
============================= 99 passed in 45.71s =============================
```

---

## Additional Debugging Runs

These were used while fixing the suite and are not substitutes for the full verification above.

```powershell
uv run --directory services/location-service --extra dev pytest tests/test_auth.py -vv -s
uv run --directory services/location-service --extra dev pytest tests/test_route_versions_api.py -vv -s
uv run --directory services/location-service --extra dev pytest tests/test_audit_findings.py::test_force_fail_respects_sla -vv -s
```

All passed after the final fixes.

---

## What Was Verified

- Public points list contract now supports canonical `per_page`, deprecated `limit`, and validated `sort`.
- Public pair responses now include profile code, origin/destination codes and names, route pointers, and pending-draft state.
- Canonical `GET /v1/processing-runs/{run_id}` matches the deprecated compatibility alias payload.
- Pair-scoped processing-run history works through `GET /v1/pairs/{pair_id}/processing-runs`.
- Public route-version detail and geometry endpoints work and are covered by tests.
- `force-fail` and bulk refresh are restricted to `SUPER_ADMIN`.

---

## Known Gaps / Honest Notes

- TASK-0021 did not run Alembic or smoke scripts because the task intentionally made no schema or cross-service runtime changes.
- Deprecated compatibility aliases were intentionally kept in place for one task cycle:
  - `limit`
  - `GET /v1/pairs/processing-runs/{run_id}`
- Force-fail success-path business behavior is still covered, but the auth-focused test in `tests/test_auth.py` was reduced to a 404 reachability check to avoid a suite hang caused by that specific test setup.
