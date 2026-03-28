# PLAN.md

## Objective

Remediate all lint warnings in the codebase to ensure high code quality and consistency.

## How I Understand the Problem

The IDE has reported 32 warnings across multiple files. Most are unused imports or unsorted imports. One is a naming convention violation (`ProblemDetail`).

## Approach

1. **Analyze and Map**: Confirm all files needing changes.
2. **Sequential Fixes**:
   - Fix naming in `errors.py` and update usages.
   - Clean up unused imports in all listed files.
   - Sort import blocks in all listed files.
3. **Verification**: Confirm warnings are gone (UI feedback).

## Files That Will Change

| File                                                                | Action | Why                                                |
| ------------------------------------------------------------------- | ------ | -------------------------------------------------- |
| services/trip-service/alembic/env.py                                | modify | Sort imports                                       |
| services/trip-service/src/trip_service/broker.py                    | modify | Remove unused `json`                               |
| services/trip-service/src/trip_service/errors.py                    | modify | Rename `ProblemDetail` -> `ProblemDetailError`     |
| services/trip-service/src/trip_service/main.py                      | modify | Sort imports                                       |
| services/trip-service/src/trip_service/middleware.py                | modify | Sort imports                                       |
| services/trip-service/src/trip_service/models.py                    | modify | Remove unused `UniqueConstraint`                   |
| services/trip-service/src/trip_service/observability.py             | modify | Sort imports, remove unused `select`               |
| services/trip-service/src/trip_service/routers/driver_statement.py  | modify | Remove unused imports and keep driver statement clean |
| services/trip-service/src/trip_service/schemas.py                   | modify | Sort imports                                       |
| services/trip-service/src/trip_service/workers/enrichment_worker.py | modify | Sort imports, remove unused `text`, `AsyncSession` |
| services/trip-service/src/trip_service/workers/outbox_relay.py      | modify | Remove unused `update`                             |
| services/trip-service/tests/conftest.py                             | modify | Sort imports                                       |
| services/trip-service/tests/test_contract.py                        | modify | Sort imports                                       |
| services/trip-service/tests/test_integration.py                     | modify | Sort imports                                       |
| services/trip-service/tests/test_unit.py                            | modify | Sort imports                                       |

## Risks

- Renaming `ProblemDetail` might miss a reference if not carefully grepped.
- Accidental removal of used imports (unlikely with UI feedback).

## Test Cases

- Verify build success.
- Check UI for zero warnings.

## Completion Criterion

- `current_problems` list is empty.
- Code is clean and strictly follows conventions.
