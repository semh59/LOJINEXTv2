# BRIEF.md

## Task
TASK-0017 — Trip Service Full Remediation (No Accepted Risks)

## Goal
Eliminate remaining Trip Service risks by fixing outbox duplicate-publish exposure in code, ensuring smoke script exits 0 on success, and validating all release-gate tests. No accepted risks.

## Scope
- Trip Service code + tests only.
- Outbox relay publish/commit safety: implement non-duplicate publish behavior.
- Smoke script exit code handling.
- Release-gate tests completeness.

## Out of Scope
- Location service or other services.
- Product changes beyond hardening.

## Success Criteria
- Outbox relay does not duplicate publish under commit failure windows.
- Smoke script returns exit code 0 when steps complete successfully.
- Trip Service test suite passes.
- All records updated with evidence.
