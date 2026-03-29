# Audit Report — Location Service Fixes (TASK-0023)

Status: Ready for review

## Fixes Applied
- Pair code generation: replaced `ulid.new()` with `ULID()` to match the installed `python-ulid` API and avoid runtime errors. File: `services/location-service/src/location_service/domain/codes.py`.
- Load/soak script: internal resolve now uses `origin_name_tr`/`destination_name_tr`; added gating to wait for ACTIVE pair with `active_forward_version_no` before internal resolve. File: `TASKS/TASK-0022/scripts/location_load.py`.
- Load/soak stability: subsequent cycles now use `/v1/pairs/{id}/refresh` instead of `/calculate` to avoid 409 conflicts on already-active pairs, with a one-time fallback to refresh if a 409 is encountered. File: `TASKS/TASK-0022/scripts/location_load.py`.
- Pytest config: added `pythonpath = ["src"]` so pytest runs without PYTHONPATH env. File: `services/location-service/pyproject.toml`.
- Smoke script noise: moved stderr suppression inside the cmd pipeline to eliminate `NativeCommandError` noise while preserving failure detection. File: `TASKS/TASK-0012/scripts/smoke.ps1`.
- Alembic clean DB upgrade: executed successfully inside docker compose stack as part of smoke. Evidence captured in `TASKS/TASK-0023/TEST_EVIDENCE.md`.

## Remaining Issues
- None observed in this task’s scope.
