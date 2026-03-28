# BRIEF.md

## Task
TASK-0015 — Trip Service Final Release-Hardening Audit

## Goal
Perform a focused, evidence-based release-hardening audit for Trip Service only. Provide PASS / FAIL / RISK ACCEPTED results across four priority areas with file/line evidence and a release checklist.

## Scope
- Service root: `services/trip-service`
- Review targets:
  - Idempotency in-flight race in `routers/trips.py`
  - Outbox publish/commit safety in `workers/outbox_relay.py`
  - Production config safety in `config.py` and startup validation
  - Release gate test sufficiency in `tests/**`

## Out of Scope
- Any code changes
- Location Service or other services

## Success Criteria
- Findings are backed by file paths, function names, and line ranges.
- Results reported in PASS / FAIL / RISK ACCEPTED format.
- Release checklist is concrete and verifiable.
