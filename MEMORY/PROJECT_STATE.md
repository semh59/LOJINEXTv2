# PROJECT_STATE.md

# Live Project State

This file answers: "Where are we right now?"
Not aspirational. Not a roadmap. Current reality only.

An out-of-date PROJECT_STATE.md is worse than no file - it misleads agents.
Update it at the end of any session that changes project state.

---

## Next Task ID

```
TASK-0013
```

Use this when creating the next task. Then increment this counter.
Never reuse a retired ID.

---

## Current Phase

```
Phase: Phase 6 - Testing
Status: in_progress
```

---

## Phase Map

```
Phase 1   Foundation & Data Model
          Produces: Project scaffold, 9 database tables, shared middleware (error handler, ETag, pagination, request ID)
          Gate: All migrations run, health endpoint returns 200, middleware unit tests pass

Phase 2   Core Trip Endpoints
          Produces: 8 core trip endpoints (ingest, create, list, detail, edit, approve, cancel, hard delete, empty return)
          Gate: All endpoint contract tests pass, all mandatory unit tests for Section 23 pass

Phase 3   Enrichment Worker & Events
          Produces: Enrichment worker with claim algorithm, retry policy, outbox relay, domain events
          Gate: Worker processes enrichment, recovers orphaned claims, outbox publishes events

Phase 4   Driver Statement
          Produces: Driver statement endpoint with stable evidence fallback
          Gate: Statement renders correctly and stays contract-compatible

Phase 5   Idempotency & Observability
          Produces: Admin idempotency, health/readiness, structured logging, metrics
          Gate: Idempotency tests pass, readiness reports correct dependency status

Phase 6   Testing
          Produces: All 44 mandatory tests from V8 spec Section 23
          Gate: All unit, integration, and contract tests pass
```

---

## Active Tasks

| Task ID   | Description                                 | Status      | Last Updated     | Last Agent  |
| --------- | ------------------------------------------- | ----------- | ---------------- | ----------- |
| TASK-0001 | Trip Service Greenfield Implementation (V8) | planning    | 2026-03-23T22:23 | Antigravity |
| TASK-0006 | Provider Adapters & Pipeline (Phase 5)      | in-progress | 2026-03-25T22:50 | Antigravity |
| TASK-0010 | Trip Service Prod Hardening                 | ready_for_review | 2026-03-27 | Codex       |
| TASK-0011 | Trip Service Contract Alignment             | ready_for_review | 2026-03-27       | Codex       |
| TASK-0012 | Deep Audit + Full Test Matrix               | in_progress | 2026-03-28       | Codex       |

---

## Recently Completed

| Task ID   | Description               | Status    | Last Updated | Last Agent  |
| --------- | ------------------------- | --------- | ------------ | ----------- |
| TASK-0009 | Location Service Imp/Exp  | completed | 2026-03-26   | Antigravity |
| TASK-0008 | Location Service Bulk     | completed | 2026-03-26   | Antigravity |
| TASK-0007 | Location Service Approval | completed | 2026-03-26   | Antigravity |
| TASK-0005 | Location Service API Endp | completed | 2026-03-25   | Antigravity |
| TASK-0004 | Location Service Domain   | completed | 2026-03-24   | Antigravity |
| TASK-0003 | Location Service Scaffo   | completed | 2026-03-24   | Antigravity |

---

## What Comes Next

```
Task:   TASK-0011 - Trip Service Contract Alignment
Why:    Deep audit and full test execution across trip-service and location-service are underway to validate the contract work before downstream adoption.
Brief:  Complete TASK-0012 (audit + lint/pytest/migrations/docker smoke), then proceed with the Tauri admin shell in TASK-0013.
```

---

## Current Blockers

| Blocker | Impact | Resolution Needed |
| ------- | ------ | ----------------- |
| -       | -      | -                 |

---

## Known Instabilities

Parts of the system that are fragile, incomplete, or temporary.

| Area | Issue | Task |
| ---- | ----- | ---- |
| Trip service public contract | TASK-0011 changes public auth and request shapes; downstream callers must migrate before release | TASK-0011 |

---

## How to Update This File

Task moved to done -> update Active Tasks and Recently Completed
Phase completed -> update Phase Map, update What Comes Next
New task created -> add to Active Tasks, increment Next Task ID
New blocker -> add to Current Blockers
New instability -> add to Known Instabilities

Do not let this file fall more than one session behind.
