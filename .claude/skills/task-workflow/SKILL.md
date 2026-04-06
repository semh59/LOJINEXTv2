---
name: task-workflow
description: Manage LOJINEXTv2 task lifecycle — create tasks, update status, and close tasks following the TASK-XXXX protocol. Use when the user asks to start a task, complete a task, update task status, or create a new task entry. Triggers include "start task", "complete task", "create task", "update PROJECT_STATE", "new TASK-XXXX".
allowed-tools: Read, Edit, Write
---

# Task Workflow Skill

## Files

| File | Purpose |
|------|---------|
| `MEMORY/PROJECT_STATE.md` | Current task table, next task ID |
| `MEMORY/KNOWN_ISSUES.md` | Active defects and drift |
| `MEMORY/DECISIONS.md` | ADR log |
| `TASKS/TASK-XXXX.md` | Per-task spec |

## Create a New Task

1. Read `MEMORY/PROJECT_STATE.md` → get the next task ID (e.g., `TASK-0047`).
2. Create `TASKS/TASK-XXXX.md` with this structure:

```markdown
# TASK-XXXX — <Title>

## Goal
<One paragraph: what done looks like>

## Scope
- <service or area>
- ...

## Steps
1. ...
2. ...

## Out of Scope
- ...

## Definition of Done
- [ ] ...
- [ ] Tests pass
- [ ] MEMORY/PROJECT_STATE.md updated
```

3. Add the task to the **Active Tasks** table in `MEMORY/PROJECT_STATE.md`:

```markdown
| TASK-XXXX | <Title> | in_progress | <YYYY-MM-DD> | <Agent> |
```

4. Increment **Next Task ID** in `MEMORY/PROJECT_STATE.md`.

## Update Task Status

Valid statuses: `in_progress` | `ready_for_review` | `blocked` | `completed`

Edit the row in `MEMORY/PROJECT_STATE.md` Active Tasks table.

## Complete a Task

1. Move the row from **Active Tasks** to **Recently Completed** in `MEMORY/PROJECT_STATE.md`.
2. Change status to `completed`.
3. Update `Last Updated` date.
4. If any known issues were resolved, remove them from `MEMORY/KNOWN_ISSUES.md`.

## Rules

- Never skip incrementing the Next Task ID.
- Never mark a task completed if tests are failing.
- Always update `PROJECT_STATE.md` as the last step of any task completion.
- If a task reveals new drift or defects, add them to `MEMORY/KNOWN_ISSUES.md` before closing.
