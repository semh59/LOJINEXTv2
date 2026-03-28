# BRIEF.md

## Task
TASK-0014 — Full Repo Detective Audit

## Goal
Perform a line-by-line audit of all code in the repository scope, capture findings with severity/impact/mitigation, and propose concrete remediation steps without changing product code. Produce a new full-repo audit report, test evidence, and a file inventory log.

## Scope
Included:
- `services/trip-service/**` (src, tests, migrations, config)
- `services/location-service/**` (src, tests, migrations, config)
- Task operational scripts:
  - `TASKS/TASK-0012/scripts/**`
  - `TASKS/TASK-0012/stubs/**`
  - `TASKS/TASK-0012/sql/**`

Excluded:
- `.git/**`, caches (`.ruff_cache`, `.uv-cache`), `storage/**` data
- Task record artifacts that are not executable or config (`TASKS/*/*.md` except where referenced)

## Out of Scope
- Product behavior changes or feature work
- Refactors outside of audit documentation and remediation guidance

## Success Criteria
- `AUDIT_REPORT_FULL_REPO.md` exists with severity-grouped findings and mitigation steps.
- `TASKS/TASK-0014/logs/file_inventory.txt` lists all audited files.
- `TASKS/TASK-0014/TEST_EVIDENCE.md` contains complete outputs for lint, pytest, migrations, and docker smoke (if run).
