# KNOWN_ISSUES.md
# Known Issues

Issues that affect the project as a whole or cross multiple areas.
Issues specific to a single component belong in that component's own docs.
Issues specific to a single task belong in TASKS/<id>/STATE.md.

Issues are never silently deleted.
When resolved: mark resolved, write what fixed it, keep the entry.

---

## How to Write an Issue

```
## [ISSUE-NNN] Short title

- **Discovered:** YYYY-MM-DD, TASK-XXXX
- **Impact:** What breaks or gets harder because of this
- **Status:** open | mitigated | resolved
- **Workaround:** What to do until it is fixed
- **Linked task:** TASK-XXXX or none
- **Resolution:** (fill when resolved — what fixed it)
```

---

## Open

## [ISSUE-001] Location Service repository-wide lint debt outside internal resolve scope

- **Discovered:** 2026-03-27, TASK-0010
- **Impact:** Running `ruff check src tests` in `services/location-service` still fails on pre-existing files unrelated to the new internal resolve endpoint, which blocks a clean repo-wide lint signal for that service.
- **Status:** open
- **Workaround:** Run targeted lint on the internal resolve files added in TASK-0010 until the existing lint findings in other location-service files are cleaned up.
- **Linked task:** TASK-0010
- **Resolution:** 

---

## [ISSUE-002] Docker smoke script returns non-zero due to PowerShell NativeCommandError

- **Discovered:** 2026-03-28, TASK-0014
- **Impact:** `TASKS/TASK-0012/scripts/smoke.ps1` can exit non-zero even when the smoke steps complete, which may cause CI or automation to treat the run as failed.
- **Status:** resolved
- **Workaround:** (resolved)
- **Linked task:** TASK-0017
- **Resolution:** Updated `TASKS/TASK-0012/scripts/smoke.ps1` to suppress PowerShell native-command error records, validate exit codes explicitly, and exit 0 on success.

---

## [ISSUE-004] Redis is now a hard runtime dependency for identity-service

- **Discovered:** 2026-04-08, TASK-0053
- **Impact:** identity-service will not start without a reachable Redis instance in `dev` and `prod` environments. `test` environment uses fakeredis (no real Redis needed).
- **Status:** open
- **Workaround:** Start Redis via `docker run -d -p 6379:6379 redis:7` or set `IDENTITY_REDIS_URL` to a managed Redis URL.
- **Linked task:** TASK-0053
- **Resolution:**

---

## [ISSUE-005] Access token revocation window: 15 minutes after user deactivation

- **Discovered:** 2026-04-08, TASK-0053
- **Impact:** When a user is deactivated via `PATCH /admin/v1/users/{id}`, their existing access tokens remain valid until expiry (up to 15 minutes). JTI blocklist only covers tokens presented at `/auth/v1/logout`. Deactivation does not enumerate and blocklist all live access tokens.
- **Status:** mitigated
- **Workaround:** Deactivation immediately revokes all refresh tokens (prevents new access token issuance). The 15-minute window is the remaining risk. `current_user` dependency re-checks `is_active` from DB on every request, so this only affects service tokens that bypass `current_user`.
- **Linked task:** TASK-0053
- **Resolution:**

---

## Resolved

## [ISSUE-003] Fleet create contracts expose `initial_spec` fields that are not applied on create

- **Discovered:** 2026-04-05, TASK-0045
- **Impact:** `fleet-service` request schemas allow `initial_spec` during vehicle and trailer create, but the create services currently ignore those fields. Internal fuel-metadata and spec-dependent flows cannot rely on inline spec initialization.
- **Status:** resolved
- **Workaround:** (resolved)
- **Linked task:** TASK-0052
- **Resolution:** Code audit in TASK-0052 confirmed `initial_spec` was already fully implemented in both `create_vehicle` (vehicle_service.py) and `create_trailer` (trailer_service.py) — spec version row is inserted within the same transaction and spec ETag is returned. Issue was filed against an earlier version of the code.
