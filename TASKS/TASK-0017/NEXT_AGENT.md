# NEXT_AGENT.md

## What is this task trying to achieve?
Eliminate remaining Trip Service risks by preventing outbox duplicate publishes and fixing smoke script exit behavior.

## What was done this session?
- Added READY/PUBLISHING statuses and updated outbox relay flow.
- Updated smoke script to avoid PowerShell NativeCommandError and exit 0 on success.
- Added outbox relay test and ran pytest.
- Ran smoke script successfully and captured evidence.
- Updated DECISIONS to supersede outbox acceptance.

## What is not done yet?
- Mark task status to `ready_for_review` or `done` after confirming records.
- Complete DONE_CHECKLIST items for git/PR if required.

## What is the riskiest thing the next agent must know?
- PUBLISHING rows will not be retried automatically; manual intervention may be needed if a publish succeeded but final commit failed.

## What is the very first action to take?
Review `TASKS/TASK-0017/TEST_EVIDENCE.md` and mark task ready for review/done.

## Which files are critical to read beyond the standard list?
- `services/trip-service/src/trip_service/workers/outbox_relay.py`
- `services/trip-service/src/trip_service/enums.py`
- `TASKS/TASK-0012/scripts/smoke.ps1`
- `TASKS/TASK-0017/TEST_EVIDENCE.md`
- `MEMORY/DECISIONS.md`

## Are there traps or non-obvious things?
- Outbox duplicate prevention trades off potential stuck PUBLISHING rows; monitor and clear if needed.

## Are there open decisions that need a human?
- None.

## What does done look like for the remaining work?
- TASK-0017 state is `ready_for_review` or `done`, checklist updated, git actions completed if required.

## What temporary implementations were introduced and where?
- None.
