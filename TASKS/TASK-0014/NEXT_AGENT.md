# NEXT_AGENT.md

## What is this task trying to achieve?
Complete a full-repo detective audit and capture test evidence without changing product code.

## What was done this session?
- Created TASK-0014 records and inventory log.
- Audited 92 scoped files and wrote `AUDIT_REPORT_FULL_REPO.md`.
- Ran ruff and pytest for trip-service and location-service.
- Ran docker smoke stack and captured output.
- Updated project memory and task records.

## What is not done yet?
- Final status flip to `ready_for_review` or `done` if you consider this task complete.
- Optional: investigate the PowerShell `NativeCommandError` emitted during docker build output in smoke logs.

## What is the riskiest thing the next agent must know?
- The docker smoke script completed functional steps but returned non-zero due to a PowerShell NativeCommandError during docker build output. This may affect automation if strict exit codes are enforced.

## What is the very first action to take?
Review `TASKS/TASK-0014/STATE.md` and decide whether to mark the task ready for review/done.

## Which files are critical to read beyond the standard list?
- `AUDIT_REPORT_FULL_REPO.md`
- `TASKS/TASK-0014/TEST_EVIDENCE.md`
- `TASKS/TASK-0014/logs/smoke.txt`

## Are there traps or non-obvious things?
- Smoke output includes a transient `curl: (52) Empty reply from server` during health probing.

## Are there open decisions that need a human?
- None.

## What does done look like for the remaining work?
- Task status set to `ready_for_review` or `done` with no additional actions required.

## What temporary implementations were introduced and where?
- None.
