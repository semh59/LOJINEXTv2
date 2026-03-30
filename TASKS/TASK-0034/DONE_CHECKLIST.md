Go through line by line.
Unchecked item without a written reason = task is not done.

---

## Core

- [x] BRIEF.md purpose fully achieved
- [x] PLAN.md reflects what was actually built
- [x] No out-of-scope changes made

## Records

- [x] CHANGED_FILES.md lists every file touched
- [x] STATE.md marked with final status and date

## Runtime

- [x] Trip API no longer spawns workers
- [x] Trip worker entrypoints exist and are runnable from package scripts
- [x] Trip `/ready` hard-gates enrichment, outbox, and cleanup worker heartbeats
- [x] Trip `/metrics` returns Prometheus output
- [x] Location API no longer dispatches background processing itself
- [x] Location processing worker claims queued/stale runs durably
- [x] Location `/ready` hard-gates processing worker heartbeat
- [x] Location `/metrics` returns Prometheus output

## Ops / Delivery

- [x] Full-stack Compose files exist for prod and CI
- [x] Ops smoke/soak/backup/restore utilities exist under `ops/trip_location`
- [x] GitHub verify and prod-gate workflows exist
- [x] Ops runbooks exist under `docs/ops`

## Tests

- [x] Targeted tests pass
- [x] TEST_EVIDENCE.md has actual output
- [x] Known gaps documented in TEST_EVIDENCE.md

## Handoff

- [x] NEXT_AGENT.md written
- [ ] Temporary code labeled `# TEMPORARY` in source
- [ ] Temporary implementations listed in NEXT_AGENT.md

## Git

- [ ] All changes committed
- [ ] Commit messages follow format in AGENTS.md
- [ ] Branch pushed
- [ ] PR opened

## Honesty

- [x] Open risks written - none hidden
- [x] Unverified things not called "working"
- [x] Temporary solutions not presented as permanent

---

## Exceptions

| Item                              | Reason                                                                                                                         |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Temporary code / TEMPORARY labels | No temporary code was introduced — all files are production-grade assets                                                       |
| Git checklist items               | This environment has not created a commit/branch/PR yet — requires user action                                                 |
| Docker integration test           | No Docker runtime available in this session; Compose stack verified through code review and cross-reference consistency checks |
