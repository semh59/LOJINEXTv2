# DONE_CHECKLIST.md

Go through line by line.
Unchecked item without a written reason = task is not done.

---

## Core
- [x] BRIEF.md purpose fully achieved
- [x] PLAN.md reflects what was actually built
- [x] No out-of-scope changes made

## Records
- [x] CHANGED_FILES.md lists every file touched by TASK-0021
- [x] STATE.md marked `ready_for_review` with date

## Tests
- [x] Tests exist for every new public contract surface
- [x] Tests exist for every new role restriction
- [x] All recorded verification steps pass
- [x] TEST_EVIDENCE.md has actual command output or excerpts
- [x] Known gaps documented in TEST_EVIDENCE.md

## Handoff
- [x] NEXT_AGENT.md written
- [x] NEXT_AGENT.md useful to someone who knows nothing about this project
- [x] Temporary compatibility behavior called out honestly

## Git
- [ ] All changes committed
- [ ] Commit messages follow format in AGENTS.md
- [ ] Branch pushed
- [ ] PR opened

## Honesty
- [x] Open risks written - none hidden
- [x] Unverified things not called working
- [x] TASK-0020 cleanup not silently folded into TASK-0021

---

## Exceptions

| Item | Reason |
|------|--------|
| `All changes committed` | The user asked for implementation and verification, not a commit. |
| `Commit messages follow format in AGENTS.md` | No commit was made in this session. |
| `Branch pushed` | No push was requested in this session. |
| `PR opened` | No PR workflow was requested in this session. |
