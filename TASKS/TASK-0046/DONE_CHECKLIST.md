# DONE_CHECKLIST.md

Go through line by line.
Unchecked item without a written reason = task is not done.

---

## Core

- [x] BRIEF.md purpose fully achieved
- [x] PLAN.md reflects what was actually built
- [x] No out-of-scope changes made

## Records

- [x] CHANGED_FILES.md lists the Phase A patch surface and the task-ledger files
- [x] STATE.md marked `done` with date

## Tests

- [x] Validation evidence recorded for `uv sync --extra dev`
- [x] Validation evidence recorded for `uv run ruff check src tests`
- [x] Validation evidence recorded for deep focused `pytest` gates
- [x] Validation evidence recorded for expanded contract/integration/worker `pytest` gate
- [x] Validation evidence recorded for `uv run pytest --cov=src/trip_service --cov-report=term-missing:skip-covered --cov-fail-under=85 -q`
- [x] Coverage thresholds from the deep test plan are met
- [x] Validation evidence recorded for route smoke from `trip_service.main`
- [x] Configured DB `--dry-run` blocker resolved with container-side execution
- [x] Real DB `--apply` recorded and verified
- [x] Real DB verification `--dry-run` recorded (reports zero drift)

## Handoff

- [x] NEXT_AGENT.md updated (Phase B cleanup is complete)
- [x] NEXT_AGENT.md useful to someone who knows nothing about this project
- [x] Temporary code removed (Phase B cleanup)
- [x] Stop conditions for real DB execution are explicit

## Honesty

- [x] Open risks written - none hidden
- [x] Unverified things not called "working"
- [x] Temporary solutions not presented as permanent

---

## Exceptions

| Item | Reason                                                    |
| ---- | --------------------------------------------------------- |
| None | All items completed during the production-parity session. |
