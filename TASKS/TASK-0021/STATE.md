# STATE.md

## Status
[ ] new
[ ] reading
[ ] planning
[ ] in_progress
[ ] blocked
[x] ready_for_review
[ ] done

## Last Updated
Date: 2026-03-29
Agent: Codex

---

## Progress Against Plan

| Step | Status |
|------|--------|
| 1. Bootstrap TASK-0021 records and memory updates | done |
| 2. Add centralized public query-contract helpers | done |
| 3. Expand frontend-facing schemas and auth roles | done |
| 4. Update public routers for points, pairs, processing, bulk refresh, and route reads | done |
| 5. Add dedicated contract and route-version tests | done |
| 6. Run verification and record evidence | done |

---

## Completed This Session

- Added `query_contracts.py` so public `page/per_page`, deprecated `limit`, and validated `sort` handling are centralized.
- Expanded public schemas with locked `ProfileCode`, enriched `PairResponse`, expanded `ProcessingRunResponse`, and new route-version/geometry/bulk-refresh responses.
- Updated Location public routers so points and pairs are frontend-complete, processing runs have canonical public endpoints, and route-version detail/geometry are publicly readable.
- Restricted public operational endpoints (`force-fail`, bulk refresh) to `SUPER_ADMIN`.
- Added dedicated contract and route-version API tests and verified the full Location test suite.

---

## Still Open

- Human review of TASK-0021.
- TASK-0020 cleanup and architecture hardening remain separate follow-up work.

---

## Blocked
[ ] Yes
[x] No

What is blocking:
What is needed:
Who resolves it:

---

## Risks Found During Build

- Pair enrichment is still query-time rather than denormalized storage. That keeps schema stable but makes router query correctness important.
- Deprecated compatibility aliases (`limit`, `/v1/pairs/processing-runs/{run_id}`) remain for one cycle and must be removed deliberately later.
- Unrelated dirty `trip-service` worktree changes were left untouched.

---

## Unexpected Findings

- A real suite hang appeared when a new auth test mixed direct DB seeding with the full force-fail happy path. The test was reduced to auth reachability, while the force-fail business path remains covered elsewhere.
- Route/version test seeding needed staged flushes because the ORM models do not declare relationships that would otherwise guarantee FK insert ordering.
