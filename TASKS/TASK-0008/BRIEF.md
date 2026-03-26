# TASK-0008: Bulk Refresh

## Purpose

Implement the Bulk Refresh orchestration to trigger re-processing of multiple Route Pairs simultaneously (Section 4.1).

## Requirements

- Support triggering by specific ID list.
- Support "Refresh All Active" global trigger.
- Orchestrate via background tasks.
- Resilient to individual run failures.
- Expose via `POST /v1/bulk-refresh/jobs`.

## Success Criteria

- [x] Bulk logic with background task integration implemented.
- [x] API endpoint integrated.
- [x] Verified with resilience integration tests.
- [x] Handoff files created.
