# NEXT_AGENT.md

You are picking up work someone else started.
That person has no memory of writing this.
Read every section. Do not skip. Do not assume.

---

## What This Task Is Trying to Achieve
Produce a location-service-only deep audit plus prod-hard test evidence focused on API/endpoint behavior, database/migrations, and contract alignment.

---

## What Was Done This Session
- Created TASK-0022 scaffold, BRIEF, PLAN, and STATE.
- Completed line-by-line audit of location-service source/tests and recorded findings in TASKS/TASK-0022/AUDIT_REPORT.md.
- Ran prod-hard test matrix:
  - `ruff check src tests` (passed)
  - `pytest` (failed without PYTHONPATH, passed with PYTHONPATH=src)
  - `alembic upgrade head` (failed due to local postgres auth)
  - Docker smoke with live providers (passed)
  - Load/soak script (failed due to internal resolve 404)
- Recorded full outputs in TASKS/TASK-0022/TEST_EVIDENCE.md.

---

## What Is Not Done Yet
1. Finalize DONE_CHECKLIST and mark task status as ready_for_review or done as appropriate.

---

## The Riskiest Thing You Need to Know
The load/soak run failed because POST /internal/v1/routes/resolve returned 404 after calculate + approve. This may indicate a timing or activation mismatch that needs investigation before calling the load test “passing.”

---

## Other Warnings
- Local alembic upgrade failed due to invalid postgres credentials; this is environment-specific, not necessarily code.

---

## Your First Action
1. Review TASKS/TASK-0022/AUDIT_REPORT.md and TASKS/TASK-0022/TEST_EVIDENCE.md.
2. Decide whether to rerun load/soak with a guard or treat the 404 as a finding.
3. Update DONE_CHECKLIST and STATE accordingly.

---

## Files Critical to Read Before Coding
- TASKS/TASK-0022/AUDIT_REPORT.md
- TASKS/TASK-0022/TEST_EVIDENCE.md
- TASKS/TASK-0022/STATE.md

---

## Files That Were Changed — Verify Before Adding To
- MEMORY/PROJECT_STATE.md
- TASKS/TASK-0022/BRIEF.md
- TASKS/TASK-0022/PLAN.md
- TASKS/TASK-0022/STATE.md
- TASKS/TASK-0022/AUDIT_REPORT.md
- TASKS/TASK-0022/TEST_EVIDENCE.md
- TASKS/TASK-0022/CHANGED_FILES.md
- TASKS/TASK-0022/scripts/location_load.py

---

## Open Decisions
- Whether to treat the internal resolve 404 in load/soak as a test failure requiring code change, or adjust the load scenario to wait for active status.

---

## Temporary Implementations

| What | Where | Permanent Solution | Task |
|------|-------|--------------------|------|
| None | - | - | - |

---

## Definition of Done for Remaining Work
- DONE_CHECKLIST updated with accurate status and exceptions.
- STATE updated to ready_for_review or done.
