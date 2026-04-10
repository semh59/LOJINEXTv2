# WORKFLOW.md
# Agent Operating Procedure

Every task passes through these phases in order.
No phase is skipped. No phase is abbreviated.

```
READ → UNDERSTAND → PLAN → BUILD → PROVE → RECORD → HAND OFF
```

---

## PHASE 1 — READ

Read everything in the mandatory reading order from AGENTS.md before touching anything.

After this phase you must know:
- what the project is trying to achieve
- what decisions have been made and why they were made that way
- what is already broken or risky
- exactly what this task needs to produce
- where the last agent stopped

**What breaks when this phase is skipped:**

Skip DECISIONS.md → you repeat a rejected decision → next agent reverts your work.
Skip KNOWN_ISSUES.md → you build on a broken foundation.
Skip NEXT_AGENT.md → you redo completed work.
Skip STATE.md → you start building without knowing you are blocked.

---

## PHASE 2 — UNDERSTAND

Before writing a plan, verify you actually understand the task.

Answer these questions. If any answer is unclear, stop, note the ambiguity in STATE.md,
and surface it before proceeding.

```
What is the single most important thing that must exist after this task?
How will I verify success?
What is explicitly out of scope?
Which files will I create or change?
What other parts of the system does this touch?
What could go wrong that BRIEF.md does not mention?
Does anything in DECISIONS.md constrain how this must be built?
Does anything in KNOWN_ISSUES.md directly affect this task?
```

If you find a contradiction between BRIEF.md and DECISIONS.md:
Mark task BLOCKED in STATE.md. Write the contradiction in NEXT_AGENT.md.
Do not resolve it yourself. The human resolves contradictions.

---

## PHASE 3 — PLAN

Write PLAN.md before writing any code.

If PLAN.md already exists: read it. Accurate → proceed. Outdated → update, then proceed.

PLAN.md must contain:

```
Objective
  One sentence: what will exist after this task that does not exist now.

How I Understand the Problem
  In your own words. Not copied from BRIEF.md.
  Differences from BRIEF.md must be noted and resolved here.

Approach
  Numbered, ordered, specific steps.
  Each step must be independently verifiable.

Files That Will Change
  Every file to create, modify, or delete.
  Nothing outside this list gets touched.
  New file needed during build → update this list first.

Risks
  What could go wrong. Honest and specific.

Test Cases
  Named cases, not types.
  Write:  "test that X cannot do Y — expects 403"
  Not:    "write tests for the endpoint"

Out of Scope
  Explicit list of what will NOT be done in this task.

Completion Criterion
  Specific, verifiable conditions.
  These become the final checklist.
```

Cannot write a clear plan → task is underspecified → mark BLOCKED, do not build.

---

## PHASE 4 — BUILD

Implement only what is in the plan.

```
Only touch files listed in PLAN.md
New file needed? → Update PLAN.md first
Scope must expand? → Update PLAN.md first
Write tests alongside each function — not after
All code, comments, and logs in English
Every function with logic gets a docstring
Configuration via environment variables — never hardcoded
Temporary code: # TEMPORARY: <reason> [see RULE-08]
```

Update STATE.md after completing each step in PLAN.md.
Do not wait until the end.
If tokens run out, STATE.md is the only map the next agent has.

**When you discover something unexpected:**

Bug outside your scope → add to `standards/KNOWN_ISSUES.md`, do not fix, continue.
Missing dependency blocks you → note in STATE.md, write NEXT_AGENT.md, stop.
Plan is wrong → add a Plan Revision section to PLAN.md, continue with corrected plan.

---

## PHASE 5 — PROVE

Run tests. Record actual output. Be honest about what was and was not verified.

Paste the full output of every test run into TEST_EVIDENCE.md.
Not a summary. Not "all tests passed." The actual output.

Honesty protocol:
```
Tests passed   → paste output, confidence: High
Some failed    → paste output, explain what failed and what you did
Not run        → write exactly why and what would enable running them
Manual only    → describe what you checked, how, and what you observed
```

Confidence level — write one in TEST_EVIDENCE.md:
```
High    automated tests cover key paths, all pass
Medium  some automated + manual checks, no failures found
Low     manual check only, or key paths not covered
None    could not run — reason documented
```

---

## PHASE 6 — RECORD

Update every file that now reflects a different reality than when you started.

Always update:
```
TASKS/<id>/STATE.md
TASKS/<id>/CHANGED_FILES.md
TASKS/<id>/TEST_EVIDENCE.md
```

Update when applicable:
```
MEMORY/PROJECT_STATE.md     overall project state changed
standards/DECISIONS.md      architectural or strategic decision was made
standards/KNOWN_ISSUES.md   cross-cutting issue found or resolved
```

Do not skip this phase because code is working.
"It works" and "I can prove it works and explain what changed" are different things.

---

## PHASE 7 — HAND OFF

Write NEXT_AGENT.md so completely that the next agent needs no other context.

NEXT_AGENT.md must answer:
```
What is this task trying to achieve? (one sentence)
What was done this session? (specific, not "worked on the service")
What is not done yet? (priority order)
What is the riskiest thing the next agent must know?
What is the very first action to take?
Which files are critical to read beyond the standard list?
Are there traps or non-obvious things?
Are there open decisions that need a human?
What does done look like for the remaining work?
What temporary implementations were introduced and where?
```

Test: read NEXT_AGENT.md as if you have never seen this project.
Do you know exactly what to do?

After writing NEXT_AGENT.md:
```bash
git add .
git commit -m "<type>(<scope>): <description> [TASK-ID]"
git push origin task/TASK-<ID>-<description>
```

Task complete → open PR to dev.
Task incomplete → wip commit + NEXT_AGENT.md is the handoff.

---

## Task Status Values

```
new               folder exists, no work started
reading           Phase 1–2
planning          writing PLAN.md
in_progress       building
blocked           cannot continue — reason in STATE.md
ready_for_review  PR opened, waiting
done              merged, DONE_CHECKLIST.md complete
```

A task at "in_progress" for multiple sessions with no progress is "blocked."

---

## Scope Management

One task, one purpose.

Second piece of work discovered:
```
1. Create TASKS/TASK-<nextID>/BRIEF.md for it
2. Increment Next Task ID in `MEMORY/PROJECT_STATE.md`
3. Note in NEXT_AGENT.md: "out of scope — new task TASK-XXXX opened"
4. Do not do it in the current task
```

---

## When Things Go Wrong

Blocked:
```
1. Write what is blocking in STATE.md
2. Write what is needed to unblock in NEXT_AGENT.md
3. Commit everything so far and push
4. Stop — do not guess through a blocker
```

Bug found outside scope:
```
1. Add to `standards/KNOWN_ISSUES.md`
2. Do not fix it here
3. Continue current task
```

Plan was wrong:
```
1. Add "Plan Revision" to PLAN.md — what changed and why
2. Continue with the corrected plan
```

Token running out:
```
1. Stop building immediately
2. Write NEXT_AGENT.md
3. Update STATE.md
4. Update CHANGED_FILES.md
5. git add . && git commit -m "wip(<scope>): checkpoint [TASK-ID]" && git push
```
