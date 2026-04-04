# PLAN.md (TASK-0043)

Phase H: Test Matrix Implementation.

## Strategy

1. **Infrastructure**: Set up `conftest.py` with `TestContainers` for PostgreSQL.
2. **Unit Tests**: Coverage for enums, ETag generation, plate normalization, and domain rules.
3. **Integration Tests**: End-to-end endpoint tests (Vehicle & Trailer CRUD) against a live DB.
4. **Contract Tests**: Verify API schemas and internal S2S contracts.
5. **Concurrency Tests**: Stress test ETag optimistic locking and outbox relay claim safety.
6. **Smoke Tests**: Final verification of readiness and health probes.

## Verification

Run `pytest` with coverage report.
