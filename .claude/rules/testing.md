# Glob: services/**/tests/**/*.py, services/**/test_*.py

## Test Standards

### Database
- Integration tests MUST use `testcontainers[postgres]` — never mock the DB.
- Each test module gets a fresh schema via Alembic migrations on the container.
- Never use SQLite as a test substitute for PostgreSQL.

### Async
- All tests use `pytest-asyncio` with `asyncio_mode = auto` (set in `pytest.ini` or `pyproject.toml`).
- Test fixtures that touch the DB must be `async def`.

### Coverage per endpoint
Every new endpoint requires at minimum:
1. Happy path — valid request, expected response.
2. Validation failure — invalid payload returns 422.
3. Auth failure — missing/invalid JWT returns 401.

### Isolation
- Tests must not depend on execution order.
- Use per-test transactions that are rolled back, or recreate schema between test runs.
- Never share mutable state between tests via module-level variables.

### Mocking
- Mock only external HTTP calls (`httpx`) and Kafka producers — not the DB.
- Use `respx` for mocking `httpx.AsyncClient` calls in unit tests.

### Running tests
```bash
cd services/<service-name>
pytest
```

### Do not
- Do not add `@pytest.mark.skip` without a linked TASK ID in the skip reason.
- Do not assert on log output as a proxy for behavior — assert on state or return values.
