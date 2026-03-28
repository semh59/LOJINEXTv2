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

## Resolved

*(none yet)*
