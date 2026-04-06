# PLAN.md

## Objective
Persist the completed `trip-service` Phase A repair evidence into the task ledger and leave a decision-complete gate for real DB backfill execution.

## How I Understand the Problem
The code patch already exists and validates locally, but the repo still lacks a dedicated task record for that work and the target DB backfill gate is unresolved. This task must document the landed change set, the exact evidence, the real blocker, and the required operator sequence without reopening `TASK-0045`.

## Approach
1. Create `TASK-0046` as a dedicated follow-up task for the `trip-service` Phase A repair and backfill gate.
2. Record the exact Phase A patch surface, validation outputs, and current blocker in the task files.
3. Update `MEMORY/PROJECT_STATE.md` so the live task ledger points to `TASK-0046` and the next available task ID becomes `TASK-0047`.

## Files That Will Change
Nothing outside this list gets touched.

| File | Action | Why |
|------|--------|-----|
| `TASKS/TASK-0046/BRIEF.md` | create | Define the task boundary and expected outcome. |
| `TASKS/TASK-0046/PLAN.md` | create | Record the execution approach and the real DB gate. |
| `TASKS/TASK-0046/STATE.md` | create | Capture current status, blocker, and open work. |
| `TASKS/TASK-0046/CHANGED_FILES.md` | create | Record the full Phase A patch file surface plus this ledger update. |
| `TASKS/TASK-0046/TEST_EVIDENCE.md` | create | Preserve the exact command outputs and remaining gaps. |
| `TASKS/TASK-0046/NEXT_AGENT.md` | create | Hand off the real DB backfill sequence and stop conditions. |
| `TASKS/TASK-0046/DONE_CHECKLIST.md` | create | Track what is already complete versus blocked or deferred. |
| `MEMORY/PROJECT_STATE.md` | modify | Point the active-task ledger at `TASK-0046`. |

## Risks
- Misreporting the Phase A patch surface would make the handoff untrustworthy.
- Marking the task complete without a reachable target DB would hide the real rollout gate.
- Mixing this task back into `TASK-0045` would blur the recovery history across unrelated scopes.

## Test Cases
- Record `uv sync --extra dev` output.
- Record `uv run ruff check src tests` output.
- Record `uv run pytest -q` output and warning context.
- Record the route smoke output from `from trip_service.main import app`.
- Record the configured DB `--dry-run` failure exactly.
- Record the ephemeral migrated Postgres `--dry-run` success exactly.

## Out of Scope
- Editing `trip-service` application code again
- Running real DB `--apply` without a healthy configured DB
- Executing Phase B strict cleanup

## Completion Criterion
- `TASKS/TASK-0046/` exists with complete brief, plan, state, changed-files, test-evidence, next-agent, and checklist files.
- `MEMORY/PROJECT_STATE.md` shows `TASK-0046` as active and `TASK-0047` as the next task ID.
- The blocker and exact real DB execution order are explicit and unambiguous.

---

## Plan Revisions

### [2026-04-05] Initial task-record plan
What changed:
- Created the documentation-only plan for the already-landed `trip-service` Phase A patch and backfill gate.
Why:
- The work needed its own task record instead of being merged into `TASK-0045`.
