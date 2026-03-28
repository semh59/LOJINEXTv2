# PLAN — TASK-0014

## Objective
Complete a line-by-line audit of the repository scope (services + operational smoke scripts), record findings with mitigation steps, and capture full test evidence without changing product code.

## How I Understand the Problem
The repository needs a full-scope audit beyond TASK-0012. The deliverable is a new audit report, a complete file inventory, and updated test evidence across the entire scoped codebase. No product changes are allowed; findings must be documented with concrete remediation guidance.

## Approach
1. Task bootstrap: create TASK-0014 records, establish logs folder, and register the task in project memory.
2. Inventory all scoped files and record the list in `TASKS/TASK-0014/logs/file_inventory.txt`.
3. Perform a line-by-line audit across the inventory using a consistent checklist (correctness, validation, authn/authz, concurrency, data integrity, performance, observability, config, dependencies, tests).
4. Write `AUDIT_REPORT_FULL_REPO.md` with findings grouped by severity and remediation steps.
5. Run lint, pytest, migration smoke checks, and the docker smoke stack; capture complete outputs in `TEST_EVIDENCE.md`.
6. Update task records (`STATE.md`, `CHANGED_FILES.md`, `NEXT_AGENT.md`).

## Files That Will Change
- `TASKS/TASK-0014/BRIEF.md`
- `TASKS/TASK-0014/PLAN.md`
- `TASKS/TASK-0014/STATE.md`
- `TASKS/TASK-0014/TEST_EVIDENCE.md`
- `TASKS/TASK-0014/CHANGED_FILES.md`
- `TASKS/TASK-0014/NEXT_AGENT.md`
- `TASKS/TASK-0014/logs/file_inventory.txt`
- `AUDIT_REPORT_FULL_REPO.md`
- `MEMORY/PROJECT_STATE.md`

## Risks
- Lint/pytest failures in location-service may persist and block a fully green signal.
- Docker smoke can be slow or produce transient warnings; evidence must include raw output.
- Audit completeness depends on accurate inventory; missing paths would reduce coverage.

## Test Cases
1. `trip-service` lint: `ruff check src tests`
2. `location-service` lint: `ruff check src tests`
3. `trip-service` pytest: `pytest`
4. `location-service` pytest: `pytest`
5. Trip migrations: `alembic upgrade head`
6. Location migrations: `alembic upgrade head`
7. Docker smoke stack (if applicable): `TASKS/TASK-0012/scripts/smoke.ps1`

## Out of Scope
- Product behavior changes or refactors
- Fixing audit findings in code

## Completion Criterion
- Audit report and file inventory are complete and stored.
- All test evidence outputs are captured verbatim.
- Task records are updated and ready for handoff.
