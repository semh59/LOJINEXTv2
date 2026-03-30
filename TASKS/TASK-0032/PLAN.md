# PLAN.md

# TASK-0032: Driver Service Deep Audit & Control Plan

## Objective

One sentence: Complete a line-by-line technical audit and remediation of the Driver Service to ensure 100% production-readiness and V2.1 spec compliance.

## How I Understand the Problem

The Driver Service is a critical master data component. While reported as complete, the "detective" requirement necessitates a deep dive into every logic branch, contract detail, and failure mode. We must ensure it's not just "working" but "hardened" according to the latest project decisions (e.g., outbox PUBLISHING state, Turkish-aware normalization, optimistic concurrency).

## Approach

1.  **Phase 1: Contract & Data Layer Audit**
    - [ ] Review `models.py` for correct indexes, constraints, and computed columns.
    - [ ] Review `schemas.py` for strict validation, role-based response shapes, and field constraints.
2.  **Phase 2: Logic & Normalization Audit**
    - [ ] Review `normalization.py`. Check Turkish name transliteration and phone E.164 edge cases.
    - [ ] Review `errors.py`. Ensure all errors follow RFC 9457 and use `ProblemDetailError`.
    - [ ] Review `serializers.py` for role-based masking (especially phone numbers for MANAGERS).
3.  **Phase 3: Router & Endpoint Audit**
    - [ ] **Public CRUD**: Check `If-Match` enforcement, audit logs, and outbox event payloads in `public.py`.
    - [ ] **Lifecycle**: Check state machine guards (BR-01 to BR-15) in `lifecycle.py`.
    - [ ] **Internal**: Check eligibility logic and security in `internal.py`.
    - [ ] **Maintenance**: Review Hard Delete (SUPER_ADMIN only, snapshot audit) and Driver Merge in `maintenance.py`.
    - [ ] **Import**: Review bulk CSV/JSON import logic, validation, and async job state in `import_jobs.py`.
4.  **Phase 4: Infrastructure & Reliability Audit**
    - [ ] Review `broker.py` & `workers.py`. Implement `PUBLISHING` state for outbox relay if missing.
    - [ ] Review `config.py` for production validations.
    - [ ] Review `main.py` for middleware and lifespan hooks.
5.  **Phase 5: Test Execution & Gap Analysis**
    - [ ] Run current test suite (`pytest`).
    - [ ] Analyze coverage (`pytest-cov`).
    - [ ] Write new tests for any identified edge-case gaps.
6.  **Phase 6: Remediation**
    - [ ] Fix all identified issues.
    - [ ] Ensure all commits follow the `<type>(<scope>): <description> [TASK-ID]` format.

## Files That Will Change

- `src/driver_service/models.py`
- `src/driver_service/schemas.py`
- `src/driver_service/normalization.py`
- `src/driver_service/serializers.py`
- `src/driver_service/errors.py`
- `src/driver_service/routers/*.py`
- `src/driver_service/workers.py`
- `src/driver_service/broker.py`
- `tests/*.py`

## Risks

- **Breaking Changes**: Audit might reveal contract inconsistencies that require changes. Downstream callers (Frontend, Trip Service) might be affected.
- **Complexity**: Import jobs and Driver Merge are complex and might hide subtle race conditions.
- **Masking**: Incorrect masking logic could leak PII to unauthorized roles.

## Test Cases

- `test_phone_masking_per_role`: Verify MANAGERS see masked phones, ADMINS see raw.
- `test_search_key_turkish_edge_cases`: Verify "İ", "I", "ğ", etc., are correctly handled in search keys.
- `test_outbox_publishing_lock`: Verify outbox relay avoids duplicate publishes during inflight status.
- `test_hard_delete_audit_snapshot`: Verify a full JSON snapshot is stored before a driver is deleted.
- `test_driver_merge_trip_check`: Verify merge is blocked if source driver has active trips.

## Out of Scope

- Integrating with a real Kafka cluster (local testing uses stubs/no-op).
- Frontend changes.

## Completion Criterion

- [ ] Line-by-line audit completed for all listed files.
- [ ] All P0/P1 issues resolved.
- [ ] 100% pass rate for the test suite.
- [ ] Documentation (AGENTS, DECISIONS, KNOWN_ISSUES) updated.
