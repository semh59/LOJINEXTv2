# TASK-0012 — Deep Audit + Full-Repo Test Execution

## Goal
Perform a line-by-line audit of `trip-service` and `location-service`, execute the full test matrix (repo-wide lint, full pytest, migration smoke, and Docker smoke stack), and publish an audit report plus test evidence.

## Scope
- Services: `trip-service`, `location-service`
- Code: all source and test files in both services
- Tests: full `ruff`, full `pytest`, migration smoke checks, Docker smoke stack

## Out of Scope
- Functional changes to product behavior
- Feature development beyond test harnesses and audit artifacts

