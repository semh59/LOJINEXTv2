# PLAN — TASK-0012

## Summary
Audit every file in `trip-service` and `location-service`, then run the full test matrix including repo-wide lint, full pytest, explicit migration checks, and a Docker smoke stack. Record findings in `AUDIT_REPORT.md` and commands in `TEST_EVIDENCE.md`.

## Steps
1. Inventory all source and test files under both services.
2. Perform a line-by-line audit and log findings with severity, impact, and mitigation.
3. Run lint for both services and record output.
4. Run full pytest for both services and record output.
5. Run explicit `alembic upgrade head` against clean DBs for both services and record output.
6. Build a disposable Docker smoke stack (Postgres + Kafka + services + stubs) and execute smoke checks.
7. Update task records and memory with the final evidence.

