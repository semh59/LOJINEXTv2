# CHANGED_FILES.md

Every file created, modified, or deleted this session.
Small changes count.

---

## Created
| File | Purpose |
|------|---------|
| `TASKS/TASK-0017/BRIEF.md` | Task brief for full remediation. |
| `TASKS/TASK-0017/PLAN.md` | Implementation plan. |
| `TASKS/TASK-0017/STATE.md` | Task status tracking. |
| `TASKS/TASK-0017/CHANGED_FILES.md` | Change log for this task. |
| `TASKS/TASK-0017/NEXT_AGENT.md` | Handoff notes. |
| `TASKS/TASK-0017/DONE_CHECKLIST.md` | Done checklist. |
| `TASKS/TASK-0017/TEST_EVIDENCE.md` | Test and smoke evidence. |
| `TASKS/TASK-0017/logs_pytest.txt` | Pytest output log. |
| `TASKS/TASK-0017/logs_smoke.txt` | Smoke script output log. |

## Modified
| File | What Changed |
|------|-------------|
| `services/trip-service/src/trip_service/enums.py` | Added outbox READY/PUBLISHING statuses. |
| `services/trip-service/src/trip_service/routers/trips.py` | Outbox rows created as READY. |
| `services/trip-service/src/trip_service/workers/outbox_relay.py` | Added PUBLISHING flow and updated selection. |
| `services/trip-service/tests/test_workers.py` | Added relay test to skip PUBLISHING rows. |
| `TASKS/TASK-0012/scripts/smoke.ps1` | Suppressed NativeCommandError and enforced exit code checks. |
| `MEMORY/DECISIONS.md` | Superseded outbox acceptance with no-duplicate decision. |
| `MEMORY/PROJECT_STATE.md` | Added TASK-0017 and advanced Next Task ID. |
| `MEMORY/KNOWN_ISSUES.md` | Marked smoke script issue resolved. |

## Deleted
| File | Why |
|------|-----|
|      |     |

---

## Notes
- Trip-service pytest and smoke script executed; see `TASKS/TASK-0017/TEST_EVIDENCE.md`.
