You are picking up work someone else started.
That person has no memory of writing this.
Read every section. Do not skip. Do not assume.

---

## What This Task Is Trying to Achieve
Fix location-service failures and lint debt from TASK-0012, then re-run tests to get green.

---

## What Was Done This Session
Implemented fixes, resolved lint/test failures, and captured test evidence in `TASKS/TASK-0013/`.

---

## What Is Not Done Yet
Priority order - most important first.

1. Optional: rerun Docker smoke if you want integration validation after these fixes.
2. Commit and PR if required by workflow.

---

## The Riskiest Thing You Need to Know
Changing ULID generation can ripple into export formats and any code that assumes a specific pair code format.

---

## Your First Action
Read `AUDIT_REPORT.md` and the location-service failure logs in `TASKS/TASK-0012/logs/`.
