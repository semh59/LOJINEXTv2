# RULES.md
# Hard Rules

Each rule closes a specific failure mode.
None have exceptions.

---

## RULE-01 — No code without a plan

PLAN.md must exist and be complete before any code is written.
Code written before PLAN.md is a draft, not deliverable work.

---

## RULE-02 — No work without a task folder

Work only begins after TASKS/<id>/ exists with BRIEF.md and STATE.md.
Work outside a task folder is invisible to every future agent.

---

## RULE-03 — One task, one purpose

A task has one primary purpose.
One task does not contain a feature + a bug fix + a refactor.
When a second piece of work is discovered, a new task is opened.

---

## RULE-04 — Only touch files listed in the plan

Files not in PLAN.md's file list are not touched.
New file needed → update PLAN.md first, then create it.

This is the primary source of side effects the next agent cannot trace.

---

## RULE-05 — Changed files must be recorded

Every file created, modified, or deleted goes in CHANGED_FILES.md
with a one-line description of what changed.

---

## RULE-06 — Test evidence is required

If a test was not run, write why in TEST_EVIDENCE.md.
Silence does not mean tests passed.
Silence means nothing was recorded.

---

## RULE-07 — Open risks are written, not hidden

Anything uncertain, fragile, temporary, or potentially wrong
is written in STATE.md or NEXT_AGENT.md.

A hidden risk multiplies. A written risk becomes a task.

---

## RULE-08 — Temporary code is labeled in source

Temporary solutions (mocks, stubs, placeholders, workarounds) are marked:

```
# TEMPORARY: <reason>
# Replace with: <what the real solution is>
# See: TASKS/<id>/BRIEF.md
```

AND listed in NEXT_AGENT.md.
Unlabeled temporary code becomes permanent.

---

## RULE-09 — Assumptions are written before acting on them

If the task requires an assumption about something not specified,
write it in PLAN.md before building on it.

Written → can be corrected before code exists.
Not written → invisible, possibly wrong, impossible to correct cleanly.

---

## RULE-10 — NEXT_AGENT.md is mandatory before leaving

A task is not left without NEXT_AGENT.md being updated.
Even for completed tasks: it records what was done so the next agent
can verify before building on it.

If tokens run out: NEXT_AGENT.md is written before anything else.

---

## RULE-11 — Memory lives in files, not in conversation

Conversation ends when the session ends.
A decision not written in MEMORY/DECISIONS.md does not exist.
The next agent will make a different decision.

---

## RULE-12 — Code and records change together

When code changes, four things change together:
- CHANGED_FILES.md reflects it
- STATE.md reflects it
- Documentation reflects it
- Git commit message describes it

Code without records does not exist from the project's perspective.

---

## RULE-13 — No mixed-concern commits

One commit, one story.
Feature + bug fix = two commits.
Refactor + new functionality = two commits.

Mixed commits make git history useless for debugging.

---

## RULE-14 — Known issues are written, not deferred silently

Something wrong that will not be fixed in this task
goes in MEMORY/KNOWN_ISSUES.md.

"I'll fix it later" with no written record means the next agent
discovers it at the worst moment.

---

## RULE-15 — Unverified things are not called working

Untested functionality is described as:
- "implemented, not yet verified"
- "not tested this session — see TEST_EVIDENCE.md"

Not as "works correctly" or "done."

---

## RULE-16 — Secrets never enter version control

No .env file is committed.
No key, token, password, or secret appears in source code.

If a secret is accidentally committed:
1. Remove from history immediately
2. Rotate the exposed credential immediately
3. Document in MEMORY/KNOWN_ISSUES.md

---

## RULE-17 — All source is in English

Code, comments, docstrings, logs, commit messages, branch names, documentation:
English only.

UI text shown to users goes through i18n — that is the only exception.

---

## RULE-18 — Phase gates are respected

No task from Phase N+1 begins until all Phase N tasks are done.

Exceptions require a written entry in MEMORY/DECISIONS.md:
- why the gate is bypassed
- what risk is accepted
- what will be done about it
