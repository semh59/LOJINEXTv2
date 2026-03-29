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
Date: 2026-03-28
Agent: Codex

---

## Progress Against Plan

| Step | Status |
|------|--------|
| 1. Bootstrap TASK-0019 records and memory updates | done |
| 2. Add Location auth, prod validation, readiness/docs gating, and global error handling | done |
| 3. Complete ETag/concurrency and approval contract cleanup | done |
| 4. Fix provider/runtime behavior and startup recovery | done |
| 5. Align Trip Service Location integration and smoke harness | done |
| 6. Update tests, run verification, and record evidence | done |

---

## Completed This Session

- Added bearer-token auth and prod fail-fast validation to `location-service`, gated docs in prod, and made `/ready` return real `503` when not ready.
- Completed the targeted pair/point ETag and `If-Match` contract, unified approval under `/approve`, and added the `/activate` tombstone.
- Fixed live provider/runtime issues: Mapbox GeoJSON parsing, provider config wiring, startup recovery, and the container-only ULID generation failure.
- Updated `trip-service` Location dependency auth/error mapping so Location business-invalid responses are no longer treated as dependency outages.
- Hardened the smoke harness and verified offline + live provider flows end to end.

---

## Still Open

- Human review of TASK-0019.
- Deferred P2 cleanup remains tracked in `TASKS/TASK-0020/`.

---

## Blocked
[ ] Yes
[x] No

What is blocking:
What is needed:
Who resolves it:

---

## Risks Found During Build

- The worktree still contains unrelated `trip-service` edits outside the TASK-0019 file set. They were left untouched.
- Processing remains in-process with startup recovery only. Persistent worker redesign is deferred to TASK-0020.

---

## Unexpected Findings

- `location-service` could pass local tests while failing in the container because `ulid-py` and `python-ulid` exposed different `ulid` APIs. TASK-0019 removed the conflicting dependency and switched to the stable `python-ulid` usage.
- Startup recovery initially assumed the schema already existed and crashed the service before migrations on a fresh DB. Recovery now skips cleanly until migrations have run.
- The smoke harness had drifted from the tightened trip rules. It now resets the stack, uses auth-aware HTTP failure checks, and uses non-conflicting test data.
