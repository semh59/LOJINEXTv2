---
description: Run tests for a specific LOJINEXTv2 service or all services
---

# Run Tests

## Instructions

1. Determine which service to test from the user's request or current context.
   - If a specific service is mentioned (e.g., "trip-service"), run tests for that service.
   - If "all" is mentioned, run tests for each service sequentially.

2. For a single service:
```bash
cd services/<service-name>
pytest -v
```

3. For all services:
```bash
for svc in trip-service fleet-service driver-service location-service identity-service; do
  echo "=== $svc ===" && cd services/$svc && pytest -v 2>&1; cd ../..
done
```

4. Report results:
   - List which tests passed / failed
   - For failures: show the test name, error message, and file:line
   - Do NOT declare success until all tests in the target service pass

## Options

- `pytest -v` — verbose output
- `pytest -x` — stop on first failure
- `pytest -k "<pattern>"` — run matching tests only
- `pytest --tb=short` — compact tracebacks

## On Failure

1. Read the error output carefully.
2. Identify if it's a test setup issue (DB container, fixture) or a real code failure.
3. Fix the root cause — do not skip or xfail tests without a TASK ID in the reason.
