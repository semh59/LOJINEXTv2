# PLAN.md

## Objective
Fix all identified location-service issues (treated as critical) and re-run the full prod-hard test matrix with clean evidence.

## How I Understand the Problem
We must correct specific defects found in TASK-0022 (pair code generation, load/soak internal resolve failure, pytest import ergonomics) and remove misleading smoke script noise, then re-run lint, pytest, alembic upgrade, docker smoke, and load/soak to produce passing evidence without altering public/internal contracts.

## Approach
1. Fix pair code generation to use python-ulid correct API.
2. Fix load/soak script to use correct names and gate resolve until active pointers exist.
3. Add pytest pythonpath config so pytest runs without PYTHONPATH env.
4. Improve smoke script to avoid misleading NativeCommandError logs while preserving failure detection.
5. Run full test matrix and capture evidence.
6. Update task records and handoff.

## Files That Will Change
Nothing outside this list gets touched.
New file needed during build -> update this list first.

| File | Action | Why |
|------|--------|-----|
| services/location-service/src/location_service/domain/codes.py | modify | Fix ULID generation runtime error. |
| TASKS/TASK-0022/scripts/location_load.py | modify | Fix internal resolve inputs and add active gating. |
| services/location-service/pyproject.toml | modify | Configure pytest pythonpath. |
| TASKS/TASK-0012/scripts/smoke.ps1 | modify | Suppress misleading NativeCommandError logs. |
| MEMORY/PROJECT_STATE.md | modify | Register TASK-0023 and advance Next Task ID. |
| TASKS/TASK-0023/BRIEF.md | modify | Task definition. |
| TASKS/TASK-0023/PLAN.md | modify | Plan details. |
| TASKS/TASK-0023/STATE.md | modify | Task status. |
| TASKS/TASK-0023/AUDIT_REPORT.md | create | Record fixes and findings. |
| TASKS/TASK-0023/TEST_EVIDENCE.md | modify | Record test outputs. |
| TASKS/TASK-0023/CHANGED_FILES.md | modify | Track file changes. |
| TASKS/TASK-0023/NEXT_AGENT.md | modify | Handoff notes. |
| TASKS/TASK-0023/DONE_CHECKLIST.md | modify | Completion checklist. |

## Risks
- Live provider smoke may fail due to API keys or rate limits.
- Load/soak can stress local resources; keep concurrency as configured.
- Alembic upgrade may depend on local DB credentials; use docker DB if needed.

## Test Cases
1. `ruff check src tests` (location-service)
2. `pytest` (location-service)
3. `alembic upgrade head` (clean DB)
4. `TASKS/TASK-0012/scripts/smoke.ps1 -UseLiveProviders`
5. `python TASKS/TASK-0022/scripts/location_load.py`

## Out of Scope
- Any contract changes.
- Trip-service fixes.

## Completion Criterion
- All five tests pass with evidence in TEST_EVIDENCE.md.
- Fixes applied without contract changes.
- Task records updated and ready_for_review.

---

## Plan Revisions

### 2026-03-29 Initial plan recorded
What changed:
- Created plan for critical fixes and retest.
Why:
- Required before implementation per RULE-01.
