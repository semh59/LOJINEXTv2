# PLAN — TASK-0015

## Objective
Produce a Trip Service-only release-hardening audit with evidence-backed findings and a final readiness decision.

## How I Understand the Problem
We need a focused, line-referenced audit of Trip Service for production readiness, centered on idempotency race handling, outbox publish/commit safety, production config fail-fast behavior, and test sufficiency for release gating.

## Approach
1. Inventory the specific Trip Service files relevant to the four audit areas.
2. Inspect idempotency claim/check/save flow and document concurrent behavior.
3. Inspect outbox relay publish/commit sequence and document failure windows.
4. Inspect production configuration defaults and any startup validation.
5. Review Trip Service tests for required scenarios and gaps.
6. Produce a structured report with PASS/FAIL/RISK ACCEPTED results.
7. Update task records for handoff.

## Files That Will Change
- `TASKS/TASK-0015/BRIEF.md`
- `TASKS/TASK-0015/PLAN.md`
- `TASKS/TASK-0015/STATE.md`
- `TASKS/TASK-0015/CHANGED_FILES.md`
- `TASKS/TASK-0015/NEXT_AGENT.md`
- `TASKS/TASK-0015/DONE_CHECKLIST.md`
- `TASKS/TASK-0015/TRIP_SERVICE_RELEASE_HARDENING_REPORT.md`
- `MEMORY/PROJECT_STATE.md`

## Risks
- Findings might be limited to static code evidence (no runtime verification).

## Test Cases
- Not applicable (audit-only task).

## Out of Scope
- Any code changes or fixes.

## Completion Criterion
- Report exists with required sections and evidence.
- Task records updated.
