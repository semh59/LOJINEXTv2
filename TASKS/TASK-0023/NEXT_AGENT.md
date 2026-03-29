# NEXT_AGENT.md

You are picking up work someone else started.
That person has no memory of writing this.
Read every section. Do not skip. Do not assume.

---

## What This Task Is Trying to Achieve
Apply critical fixes from TASK-0022 and re-run the full prod-hard test matrix with evidence.

---

## What Was Done This Session
- Updated ULID generation to use `ULID()` in `services/location-service/src/location_service/domain/codes.py`.
- Fixed load/soak script to use `origin_name_tr`/`destination_name_tr`, added ACTIVE gating, and switched to refresh after first cycle in `TASKS/TASK-0022/scripts/location_load.py`.
- Added pytest `pythonpath = ["src"]` in `services/location-service/pyproject.toml`.
- Suppressed `NativeCommandError` noise in `TASKS/TASK-0012/scripts/smoke.ps1` by moving stderr suppression into the cmd pipeline.
- Ran full test matrix and captured outputs in `TASKS/TASK-0023/TEST_EVIDENCE.md`.

---

## What Is Not Done Yet
Priority order — most important first.

1. Review evidence and mark TASK-0023 as done if acceptable.

---

## The Riskiest Thing You Need to Know
Live smoke uses external provider keys; reruns may fail due to rate limits or missing keys.

---

## Other Warnings
Repository has many unrelated dirty changes; avoid reverting them.

---

## Your First Action

1. Review `TASKS/TASK-0023/TEST_EVIDENCE.md`.
2. Confirm fixes in `TASKS/TASK-0023/AUDIT_REPORT.md`.
3. If satisfied, mark STATE.md as done.

---

## Files Critical to Read Before Coding
- `TASKS/TASK-0023/BRIEF.md`
- `TASKS/TASK-0023/PLAN.md`
- `TASKS/TASK-0023/AUDIT_REPORT.md`
- `TASKS/TASK-0023/TEST_EVIDENCE.md`

---

## Files That Were Changed — Verify Before Adding To
- `services/location-service/src/location_service/domain/codes.py`
- `TASKS/TASK-0022/scripts/location_load.py`
- `services/location-service/pyproject.toml`
- `TASKS/TASK-0012/scripts/smoke.ps1`

---

## Open Decisions
None.

---

## Temporary Implementations

| What | Where | Permanent Solution | Task |
|------|-------|--------------------|------|
| None | N/A | N/A | N/A |

---

## Definition of Done for Remaining Work
- TASK-0023 marked done after review.
