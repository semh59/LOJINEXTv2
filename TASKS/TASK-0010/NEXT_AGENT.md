# NEXT_AGENT.md

You are picking up work someone else started.
That person has no memory of writing this.
Read every section. Do not skip. Do not assume.

---

## What This Task Is Trying to Achieve
Make trip-service production-safe on its locked contracts and add the missing location-service internal route resolve endpoint it depends on.

---

## What Was Done This Session
Implemented the trip-service hardening plan: strict timezone/enum/admin validation, transactional idempotency replay with stored headers, named uniqueness/empty-return DB protections, fleet validation client calls, Kafka broker wiring, hard readiness, worker heartbeats, retry fixes, Docker packaging, Alembic-backed tests, and the missing location-service internal route resolve endpoint with tests.

---

## What Is Not Done Yet
Priority order - most important first.

1. Implement trip-service contract, persistence, broker, readiness, and worker hardening.
2. If required, automate the multi-service Docker smoke stack that was still only verified via image build/import smoke in TASK-0010.
3. Clean up the pre-existing repo-wide location-service lint debt noted in `MEMORY/KNOWN_ISSUES.md`.

---

## The Riskiest Thing You Need to Know
Trip-service is now hard-gated on downstream probes and worker heartbeats; tests and local tooling must explicitly stub or satisfy those dependencies or readiness will fail by design.

---

## Other Warnings

- The worktree is already dirty from prior trip-service cleanup work.
- Fleet-service implementation does not exist in this repo; only the client contract can be coded here.
- A full docker-compose style smoke stack was not added in this task; only Docker image build/import smoke was verified.

---

## Your First Action

1. Continue from `TASKS/TASK-0010/PLAN.md`.
2. Read `TASKS/TASK-0010/TEST_EVIDENCE.md` before changing any hardened behavior.
3. Decide whether the next work item is docker-stack automation or unrelated follow-up, and open a new task if scope changes.

---

## Files Critical to Read Before Coding

- `TASKS/TASK-0010/PLAN.md`
- `services/trip-service/src/trip_service/routers/trips.py`
- `services/trip-service/src/trip_service/workers/enrichment_worker.py`
- `services/trip-service/src/trip_service/workers/outbox_relay.py`
- `services/trip-service/src/trip_service/dependencies.py`
- `services/location-service/src/location_service/routers/internal_routes.py`

---

## Files That Were Changed - Verify Before Adding To

- `TASKS/TASK-0010/BRIEF.md`
- `TASKS/TASK-0010/PLAN.md`
- `TASKS/TASK-0010/STATE.md`
- `TASKS/TASK-0010/CHANGED_FILES.md`
- `TASKS/TASK-0010/TEST_EVIDENCE.md`
- `services/trip-service/src/trip_service/routers/trips.py`
- `services/location-service/src/location_service/routers/internal_routes.py`

---

## Open Decisions
Questions that need a human to resolve.
If answerable from DECISIONS.md or BRIEF.md, answer yourself.

- None at this stage. The user already locked the key rollout decisions for this task.
- None pending for TASK-0010. Follow-up work should open a new task rather than extending this one silently.

---

## Temporary Implementations

| What | Where | Permanent Solution | Task |
|------|-------|--------------------|------|
| None introduced | - | - | TASK-0010 |

---

## Definition of Done for Remaining Work

- Trip-service contracts, tests, Docker image build, and memory files are all green and recorded.
- Location-service internal resolve endpoint is implemented and its targeted lint/tests pass.
- Any future work is a new task, not an extension of TASK-0010.
