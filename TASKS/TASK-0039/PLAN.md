# PLAN.md (TASK-0039)

Phase D: Vehicle Spec Versions.

## Strategy

1. **Spec Service**: Implement `vehicle_spec_service.py`.
2. **Temporal Logic**: Handle `effective_from_utc` and GiST overlap guards.
3. **As-Of Queries**: Implement temporal queries to retrieve history.
4. **Spec ETags**: Distinct stream versioning separate from Master status.

## Verification

Integration tests for spec creation and overlap detection.
