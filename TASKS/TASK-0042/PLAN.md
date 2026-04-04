# PLAN.md (TASK-0042)

Phase G: Outbox Worker + Readiness.

## Strategy

1. **Outbox Relay**: Implement background worker for event publishing.
2. **Claim Mechanism**: Locking for concurrent worker safety.
3. **Dead-Lettering**: Handle failed events or hard deletes.
4. **Probes**: Implement `/health` and `/ready` endpoints.

## Verification

Smoke tests for probes and integration tests for outbox processing.
