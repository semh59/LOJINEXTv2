# PLAN.md

## Context
TASK-0012 identified location-service defects and lint failures. This plan focuses on making location-service green again while preserving current contracts.

## Inputs
- Audit findings: [AUDIT_REPORT.md](/d:/PROJECT/LOJINEXTv2/AUDIT_REPORT.md)
- Evidence logs: [TEST_EVIDENCE.md](/d:/PROJECT/LOJINEXTv2/TASKS/TASK-0012/TEST_EVIDENCE.md)

## Work Plan
1. Fix `generate_pair_code()` `TypeError` in [codes.py](/d:/PROJECT/LOJINEXTv2/services/location-service/src/location_service/domain/codes.py).
   - Replace `ulid.ULID()` with a correct ULID generation API.
   - Add or update a unit test to validate correct string format and non-crashing behavior.
   - Validate all call sites that use pair codes still expect the same format.

2. Align tests with actual optimistic locking contract.
   - Update `tests/test_points_api.py` to include `If-Match` in PATCH when required, or adjust API to allow no `If-Match` if the contract is meant to be optional.
   - Document the expected behavior in the test name and assertions.

3. Fix test isolation in `test_schema_integration.py`.
   - Ensure fixture isolation or unique test data per test run.
   - Remove shared hard-coded codes that collide with unique constraints.

4. Clear lint failures.
   - Run `ruff check src tests --fix` and ensure all import ordering and unused imports are corrected.
   - Verify no new lint regressions appear.

5. Re-run test matrix and update evidence.
   - `uv run --directory services/location-service --extra dev ruff check src tests`
   - `uv run --directory services/location-service --extra dev pytest`
   - Optionally re-run the Docker smoke script if location-service behavior changes could affect integration.
   - Update `TASKS/TASK-0013/TEST_EVIDENCE.md` and logs.

## Acceptance Criteria
- Location-service unit and integration tests pass.
- Lint passes with zero errors.
- No new audit-level regressions in location-service behavior.

## Risks
- Fixing ULID generation could change code format expectations. Confirm any formatting assumptions in tests and export paths.
- If contract requires `If-Match` on PATCH, client tests must be updated accordingly.

