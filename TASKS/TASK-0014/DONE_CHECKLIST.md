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
- [ ] STATE.md marked `done` with date

## Tests
- [ ] Tests exist for every new piece of logic
- [ ] Tests exist for every error path
- [ ] All tests pass
- [x] TEST_EVIDENCE.md has actual output — not a summary
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
- [x] Open risks written — none hidden
- [x] Unverified things not called "working"
- [x] Temporary solutions not presented as permanent

---

## Exceptions

| Item | Reason |
|------|--------|
| STATE.md marked `done` with date | Task left at `ready_for_review` pending git/PR and smoke exit non-zero note. |
| Tests exist for every new piece of logic | No new product logic added in this audit-only task. |
| Tests exist for every error path | No new product logic added in this audit-only task. |
| All tests pass | Docker smoke returned non-zero exit due to PowerShell NativeCommandError; functional steps completed (see TEST_EVIDENCE). |
| All changes committed | Git commit not performed in this session. |
| Commit messages follow format in AGENTS.md | No commit created. |
| Branch pushed | No push performed. |
| PR opened | No PR opened. |
