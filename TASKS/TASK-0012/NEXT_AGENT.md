You are picking up work someone else started.
That person has no memory of writing this.
Read every section. Do not skip. Do not assume.

---

## What This Task Is Trying to Achieve
Run a full deep audit of trip-service and location-service, plus a full test matrix including Docker smoke, and publish a severity-ranked `AUDIT_REPORT.md` with evidence.

---

## What Was Done This Session
Completed full line-by-line audit, ran lint/pytest for both services, executed Docker smoke stack, and recorded findings in `AUDIT_REPORT.md` with evidence logs in `TASKS/TASK-0012/logs/`.

---

## What Is Not Done Yet
Priority order - most important first.

1. None for TASK-0012. If you pick this up, you are likely implementing fixes based on `AUDIT_REPORT.md`.

---

## The Riskiest Thing You Need to Know
Location-service still has repo-wide lint debt and failing tests; do not hide or bypass these. Fixes must be explicit and tracked.

---

## Other Warnings

- The worktree is already dirty from prior tasks; do not revert unrelated user changes.
- TASK-0010 and TASK-0011 changes are still uncommitted and must remain the base.

---

## Your First Action

1. Read `AUDIT_REPORT.md` and the evidence logs under `TASKS/TASK-0012/logs/`.
2. Decide whether to open a new task (e.g., TASK-0013) to fix the highest-severity items.

---

## Files Critical to Read Before Coding

- `services/trip-service/src/trip_service/**`
- `services/trip-service/tests/**`
- `services/location-service/src/location_service/**`
- `services/location-service/tests/**`

---

## Files That Were Changed - Verify Before Adding To

- `TASKS/TASK-0012/BRIEF.md`
- `TASKS/TASK-0012/PLAN.md`
- `TASKS/TASK-0012/STATE.md`
- `TASKS/TASK-0012/CHANGED_FILES.md`
- `TASKS/TASK-0012/TEST_EVIDENCE.md`
- `TASKS/TASK-0012/NEXT_AGENT.md`
- `TASKS/TASK-0012/DONE_CHECKLIST.md`

---

## Open Decisions
Questions that need a human to resolve.
If answerable from DECISIONS.md or BRIEF.md, answer yourself.

- None yet. This task is purely audit and test execution.

---

## Temporary Implementations

| What | Where | Permanent Solution | Task |
|------|-------|--------------------|------|
| None yet | - | - | TASK-0012 |

---

## Definition of Done for Remaining Work

- `AUDIT_REPORT.md` is complete with severity-ranked findings and file references.
- `TEST_EVIDENCE.md` includes full command outputs for lint, pytest, migrations, and Docker smoke.
