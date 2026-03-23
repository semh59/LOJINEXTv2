# PROJECT_STATE.md

# Live Project State

This file answers: "Where are we right now?"
Not aspirational. Not a roadmap. Current reality only.

An out-of-date PROJECT_STATE.md is worse than no file — it misleads agents.
Update it at the end of any session that changes project state.

---

## Next Task ID

```
TASK-0001
```

Use this when creating the next task. Then increment this counter.
Never reuse a retired ID.

---

## Current Phase

```
Phase: —
Status: not started
```

---

## Phase Map

Define phases here as the project is planned.
Each phase entry must include:

- what the phase produces
- the gate condition that closes it

```
Phase X   [Name]
          Produces: [what working software exists after this phase]
          Gate: [specific, verifiable condition — not "it works"]
```

---

## Active Tasks

| Task ID | Description | Status | Last Updated | Last Agent |
| ------- | ----------- | ------ | ------------ | ---------- |
| —       | —           | —      | —            | —          |

---

## Recently Completed

| Task ID | Description | Completed | Merged |
| ------- | ----------- | --------- | ------ |
| —       | —           | —         | —      |

---

## What Comes Next

```
Task:   —
Why:    —
Brief:  —
```

---

## Current Blockers

| Blocker | Impact | Resolution Needed |
| ------- | ------ | ----------------- |
| —       | —      | —                 |

---

## Known Instabilities

Parts of the system that are fragile, incomplete, or temporary.

| Area | Issue | Task |
| ---- | ----- | ---- |
| —    | —     | —    |

---

## How to Update This File

Task moved to done → update Active Tasks and Recently Completed
Phase completed → update Phase Map, update What Comes Next
New task created → add to Active Tasks, increment Next Task ID
New blocker → add to Current Blockers
New instability → add to Known Instabilities

Do not let this file fall more than one session behind.
