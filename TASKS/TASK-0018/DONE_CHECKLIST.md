# DONE_CHECKLIST.md

Go through line by line.
Unchecked item without a written reason = task is not done.

---

## Core
- [x] BRIEF.md purpose fully achieved
- [x] PLAN.md reflects what was actually built
- [x] No out-of-scope changes made

## Records
- [x] CHANGED_FILES.md lists every file touched
- [x] STATE.md marked `done` with date

## Tests
- [x] Tests exist for every new piece of logic
- [x] Tests exist for every error path
- [x] All tests pass
- [x] TEST_EVIDENCE.md has actual output - not a summary
- [x] Known gaps documented in TEST_EVIDENCE.md

## Handoff
- [x] NEXT_AGENT.md written
- [x] NEXT_AGENT.md useful to someone who knows nothing about this project
- [x] Temporary code labeled `# TEMPORARY` in source
- [x] Temporary implementations listed in NEXT_AGENT.md

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

| Item | Reason |
|------|--------|
| `All changes committed` | User asked for implementation; no commit was requested in this session. |
| `Branch pushed` | No push was requested in this session. |
| `PR opened` | No PR workflow was requested in this session. |
| `Temporary code labeled # TEMPORARY in source` | No temporary source implementation was left behind. |
| `Temporary implementations listed in NEXT_AGENT.md` | No temporary implementation remains to hand off. |
