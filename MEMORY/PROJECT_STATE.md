# PROJECT_STATE.md

# Live Project State

This file answers: "Where are we right now?"
Not aspirational. Not a roadmap. Current reality only.

An out-of-date PROJECT_STATE.md is worse than no file - it misleads agents.
Update it at the end of any session that changes project state.

---

## Next Task ID

```
TASK-0036
```

Use this when creating the next task. Then increment this counter.
Never reuse a retired ID.

---

## Active Tasks

| ID        | Title                                | Status           | Started    | Agent       |
| --------- | ------------------------------------ | ---------------- | ---------- | ----------- |
| TASK-0034 | Trip/Location Full Prod Readiness    | ready_for_review | 2026-03-30 | Antigravity |
| TASK-0035 | Audit Remediation Phase 1: Readiness | in_progress      | 2026-04-02 | Antigravity |

---

## Current Phase

```
Phase: Phase 7 - Production Ready
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

Phase 7   Production Ready
          Produces: split worker topology, durable processing worker, release compose stack, monitoring package, smoke/soak automation, release gate workflows
          Gate: targeted tests pass, full-stack smoke succeeds, release gate assets exist
```

---

## Active Tasks

| Task ID   | Description                                      | Status           | Last Updated     | Last Agent  |
| --------- | ------------------------------------------------ | ---------------- | ---------------- | ----------- |
| TASK-0001 | Trip Service Greenfield Implementation (V8)      | planning         | 2026-03-23T22:23 | Antigravity |
| TASK-0006 | Provider Adapters & Pipeline (Phase 5)           | in-progress      | 2026-03-25T22:50 | Antigravity |
| TASK-0010 | Trip Service Prod Hardening                      | ready_for_review | 2026-03-27       | Codex       |
| TASK-0011 | Trip Service Contract Alignment                  | ready_for_review | 2026-03-27       | Codex       |
| TASK-0012 | Deep Audit + Full Test Matrix                    | in_progress      | 2026-03-28       | Codex       |
| TASK-0014 | Full Repo Detective Audit                        | ready_for_review | 2026-03-28       | Codex       |
| TASK-0018 | Location Service Contract Cleanup                | ready_for_review | 2026-03-28       | Codex       |
| TASK-0019 | Location Release Hardening + Trip Alignment      | ready_for_review | 2026-03-28       | Codex       |
| TASK-0020 | Location Cleanup and Architecture Hardening      | planning         | 2026-03-28       | Codex       |
| TASK-0021 | Location Frontend Contract Alignment             | ready_for_review | 2026-03-29       | Codex       |
| TASK-0022 | Location Service Deep Audit + Prod-Hard Tests    | ready_for_review | 2026-03-29       | Codex       |
| TASK-0023 | Location Service Critical Fixes + Retest         | completed        | 2026-03-29       | Codex       |
| TASK-0024 | Driver Service Scaffold & Database               | completed        | 2026-03-30       | Antigravity |
| TASK-0025 | Driver Service CRUD Endpoints                    | completed        | 2026-03-30       | Antigravity |
| TASK-0026 | Driver Service Lifecycle Endpoints               | completed        | 2026-03-30       | Antigravity |
| TASK-0027 | Driver Service Internal Endpoints & Events       | completed        | 2026-03-30       | Antigravity |
| TASK-0028 | Driver Service Import Flow                       | completed        | 2026-03-30       | Antigravity |
| TASK-0029 | Driver Service Hard Delete + Merge               | completed        | 2026-03-30       | Antigravity |
| TASK-0030 | Driver Service Final Test Matrix + Observability | completed        | 2026-03-30       | Antigravity |
| TASK-0031 | Driver Service Refining tasks & Import Tests     | completed        | 2026-03-30       | Antigravity |
| TASK-0032 | Driver Service Production Audit & Hardening      | completed        | 2026-03-30       | Antigravity |
| TASK-0033 | Trip/Location Audit Remediation                  | completed        | 2026-03-30       | Codex       |
| TASK-0034 | Trip/Location Full Production Readiness          | ready_for_review | 2026-03-30       | Antigravity |

---

## Recently Completed

| Task ID   | Description                                 | Status    | Last Updated | Last Agent  |
| --------- | ------------------------------------------- | --------- | ------------ | ----------- |
| TASK-0033 | Trip/Location Audit Remediation             | completed | 2026-03-30   | Codex       |
| TASK-0032 | Driver Service Production Audit & Hardening | completed | 2026-03-30   | Antigravity |
| TASK-0017 | Trip Service Full Remediation               | completed | 2026-03-28   | Codex       |
| TASK-0016 | Trip Service Release-Hardening Fixes        | completed | 2026-03-28   | Codex       |
| TASK-0015 | Trip Service Release-Hardening Audit        | completed | 2026-03-28   | Codex       |
| TASK-0009 | Location Service Imp/Exp                    | completed | 2026-03-26   | Antigravity |
| TASK-0008 | Location Service Bulk                       | completed | 2026-03-26   | Antigravity |
| TASK-0007 | Location Service Approval                   | completed | 2026-03-26   | Antigravity |
| TASK-0005 | Location Service API Endp                   | completed | 2026-03-25   | Antigravity |

---

## What Comes Next

```
Task:   TASK-0034 - Trip/Location Full Production Readiness
Why:    The services now need production packaging beyond correctness fixes: split runtimes, durable worker execution, full-stack compose assets, monitoring, and release-gated verification.
Brief:  Separate API/worker processes, move Location processing onto claimed workers, add production deploy/ops assets, and wire release verification into the repo.
```

---

## Current Blockers

| Blocker | Impact | Resolution Needed |
| ------- | ------ | ----------------- |
| -       | -      | -                 |

---

## Known Instabilities

Parts of the system that are fragile, incomplete, or temporary.

| Area                                  | Issue                                                                                                           | Task      |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------- | --------- |
| Trip/location production packaging    | Compose stack, ops scripts, CI workflows, and runbooks created but not Docker-integration-tested                | TASK-0034 |
| Location public compatibility aliases | TASK-0021 intentionally keeps `limit` and the deprecated pair-prefixed processing-run detail path for one cycle | TASK-0020 |

---

## How to Update This File

Task moved to done -> update Active Tasks and Recently Completed
Phase completed -> update Phase Map, update What Comes Next
New task created -> add to Active Tasks, increment Next Task ID
New blocker -> add to Current Blockers
New instability -> add to Known Instabilities

Do not let this file fall more than one session behind.
