# TASK-0054: Plan

## Approach
Create `tests/test_production_certification.py` with ~30 tests across 4 sections:
1. Unit: hash stability, header normalization matrix, status normalization, exclusion logic
2. Integration: idempotency replays, soft-delete driver/vehicle release, listing filters
3. Concurrency: 10-worker stress, outbox atomicity, fleet 503/timeout resilience
4. Contract: RFC 9457 field audit, ETag consistency for PATCH/approve/cancel

## Files
- Create: `services/trip-service/tests/test_production_certification.py`
- Create: `TASKS/TASK-0054/{BRIEF,PLAN,STATE,NEXT_AGENT}.md`
- Update: `MEMORY/PROJECT_STATE.md`