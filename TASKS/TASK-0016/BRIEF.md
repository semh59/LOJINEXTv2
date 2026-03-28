# BRIEF.md

## Task
TASK-0016 — Trip Service Release-Hardening Fixes

## Goal
Implement hardening fixes for Trip Service: idempotency in-flight handling, production fail-fast config validation, release-gate tests, and documented acceptance of outbox duplicate-publish risk.

## Scope
- Trip Service code and tests only.
- Add new problem detail for idempotency in-flight conflict.
- Add prod validation in config/startup.
- Add release-gate tests listed in TASK-0015 report.
- Document outbox at-least-once tradeoff in MEMORY/DECISIONS.md.

## Out of Scope
- Location service or other services.
- Functional product changes not required for hardening.

## Success Criteria
- In-flight idempotency returns controlled 409/425 response (no 5xx).
- Prod boot fails fast on default/insecure config.
- Required release-gate tests exist and pass.
- Outbox duplicate-publish risk is explicitly documented.
