# AGENTS.md

# Agent Constitution

---

## Why This File Exists

You are an AI agent. You have no memory of previous sessions.
Every assumption you carry into this session that is not written in these files is wrong.

These are the failure modes this system was built to prevent:

- Work is repeated because the agent did not know it was already done.
- A decision is made that contradicts one already recorded.
- Files are changed outside the task scope, creating invisible side effects.
- The task is marked done but the next agent cannot continue safely.
- Token runs out and all progress is lost with no trace.

Every file in this system closes one of those gaps.

---

## Mandatory Reading Order

Do not write a single line of code before reading these in order:

```
1.  .agents/docs/AGENTS.md             ← you are here
2.  .agents/docs/WORKFLOW.md           ← how to work
3.  .agents/docs/RULES.md              ← what is never allowed
4.  MEMORY/PROJECT_STATE.md            ← where the project stands now
5.  MEMORY/DECISIONS.md                ← why things are the way they are
6.  MEMORY/KNOWN_ISSUES.md             ← what is already broken or risky
7.  TASKS/<your-task>/BRIEF.md         ← what this task must produce
8.  TASKS/<your-task>/PLAN.md          ← how (write this if it does not exist)
9.  TASKS/<your-task>/STATE.md         ← where the last agent stopped
10. TASKS/<your-task>/NEXT_AGENT.md    ← notes left specifically for you
```

This takes 10–15 minutes. It prevents 2–3 hours of wrong work.

---

## How Memory Works

An agent's memory ends when the session ends.
This system replaces that lost memory with files.

```
MEMORY/              Project-level memory
                     Decisions, current state, known issues

TASKS/<id>/          Task-level memory
                     What to build, how to build it,
                     where we stopped, what comes next
```

Any decision not written in MEMORY/DECISIONS.md does not exist.
The next agent will make a different decision and create a conflict.

---

## How Tasks Work

Every piece of work lives in its own folder under TASKS/.
That folder contains everything needed to start, continue, and hand off the work.

```
TASKS/
  _TEMPLATE/     copy this to start a new task
  TASK-0001/
  TASK-0002/
  ...
```

A task ID is assigned before any work begins.
The next available ID is always in MEMORY/PROJECT_STATE.md under "Next Task ID."

---

## How Handoff Works

When a session ends — planned or due to token limits — the agent leaves:

```
STATE.md          current status and progress against the plan
CHANGED_FILES.md  every file touched this session
TEST_EVIDENCE.md  what was tested and the actual output
NEXT_AGENT.md     everything the next agent needs to continue
```

Without these four files, the session's work is effectively lost.
Writing them is not optional. It is the job.

---

## The Complete Job

```
READ → PLAN → BUILD → PROVE → RECORD → HAND OFF
```

Writing code is one step in the middle.
The steps before and after are equally required.

---

## Git

Git is the audit trail. Every meaningful state lives in Git.

### Branch structure

```
main         always deployable — direct commits forbidden
             merged from dev, CI must pass

dev          integration branch — direct commits forbidden
             merged to main when a phase completes

task/TASK-<ID>-<short-description>
             one branch per task, created from dev
             merged to dev via PR when task is done
```

### Commit format

```
<type>(<scope>): <description> [TASK-ID]

Types: feat | fix | test | docs | refactor | chore | migration | wip

wip is for session checkpoints when work is incomplete.
Every session ends with a push — even wip.
```

### Non-negotiable commit rules

```
Never commit secrets, credentials, or .env files
Never commit code that fails its own tests (except wip checkpoints)
Every session ends with a push
```

---

## Definition of Done

A task is done when a stranger can safely build on it.

```
[ ] BRIEF.md purpose is fully achieved
[ ] PLAN.md reflects what was actually built
[ ] CHANGED_FILES.md lists every file touched
[ ] Tests ran and output is in TEST_EVIDENCE.md
[ ] No out-of-scope changes were made
[ ] Open risks are written — none hidden
[ ] NEXT_AGENT.md is written for someone who knows nothing
[ ] DONE_CHECKLIST.md is fully checked
[ ] Branch committed, pushed, PR opened
```
