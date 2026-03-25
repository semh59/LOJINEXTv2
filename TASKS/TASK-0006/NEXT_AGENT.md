# Notes for the Next Agent

## Context

You are continuing the Location Service implementation. We have finished the Processing Pipeline (TASK-0006) except for the final integration test verification because Docker/Testcontainers was unavailable.

## Key Files

- `src/location_service/processing/pipeline.py`: The 30-step algorithm.
- `src/location_service/routers/processing.py`: Calculation trigger endpoints.
- `tests/test_processing_flow.py`: The integration test you need to run.

## Watch Out For

- `conftest.py` was modified to remove `autouse=True` from the `postgres_container` fixture. This allows unit tests (non-DB) to run without Docker. You MUST manually include `postgres_container` in any fixture or test that needs a real DB.
- Hashing logic in `domain/hashing.py` now accepts dictionaries for canonicalization.

## Immediate Next Steps

1. Verify if Docker is running.
2. Run `pytest tests/test_processing_flow.py -v --postgres-container` (you may need to add it to the command or fixtures).
3. If tests pass, move to TASK-0007 (Approval Flow).
