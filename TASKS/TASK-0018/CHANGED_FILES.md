# CHANGED_FILES.md

Every file created, modified, or deleted this session.
Small changes count.

---

## Created
| File | Purpose |
|------|---------|
| `TASKS/TASK-0018/BRIEF.md` | Task definition for TASK-0018 |
| `TASKS/TASK-0018/PLAN.md` | Execution plan and scope lock |
| `TASKS/TASK-0018/STATE.md` | Session progress and completion state |
| `TASKS/TASK-0018/CHANGED_FILES.md` | File ledger for the task |
| `TASKS/TASK-0018/TEST_EVIDENCE.md` | Verification evidence |
| `TASKS/TASK-0018/DONE_CHECKLIST.md` | Completion checklist |
| `TASKS/TASK-0018/NEXT_AGENT.md` | Handoff summary |
| `services/location-service/alembic/versions/0d5f12e97db6_remove_import_export.py` | Forward migration to remove import/export schema |

## Modified
| File | What Changed |
|------|-------------|
| `MEMORY/DECISIONS.md` | Recorded that Location Service no longer owns import/export responsibilities |
| `MEMORY/PROJECT_STATE.md` | Added TASK-0018 and marked it ready for review |
| `services/location-service/.env.example` | Removed dead storage/import/export env surface |
| `services/location-service/pyproject.toml` | Removed `openpyxl` and `python-multipart` dependencies |
| `services/location-service/uv.lock` | Synced lockfile after dependency removal |
| `services/location-service/src/location_service/config.py` | Removed import/export/storage settings |
| `services/location-service/src/location_service/enums.py` | Removed import/export-specific enums and kept historical `IMPORT_CALCULATE` |
| `services/location-service/src/location_service/errors.py` | Added request-validation problem+json handling and cleaned dead errors |
| `services/location-service/src/location_service/main.py` | Removed import/export router registration and registered validation handler |
| `services/location-service/src/location_service/middleware.py` | Added reusable If-Match mismatch factory support |
| `services/location-service/src/location_service/models.py` | Removed import/export ORM models and `ProcessingRun.import_job_id` |
| `services/location-service/src/location_service/observability.py` | Removed import/export metrics |
| `services/location-service/src/location_service/processing/approval.py` | Centralized approve/discard state mutation and pair row-version increments |
| `services/location-service/src/location_service/processing/bulk.py` | Aligned trigger type usage with enum values |
| `services/location-service/src/location_service/processing/pipeline.py` | Persisted pair route IDs, incremented pair row_version, and normalized trigger types |
| `services/location-service/src/location_service/routers/approval.py` | Routed activate/discard through shared approval logic |
| `services/location-service/src/location_service/routers/internal_routes.py` | Enforced ACTIVE-version-only resolve and ambiguity handling |
| `services/location-service/src/location_service/routers/pairs.py` | Fixed soft-deleted duplicate handling, `is_active` filtering, `If-Match`, and row_version updates |
| `services/location-service/src/location_service/routers/points.py` | Added blank-name/code/coordinate validation and stable integrity-error mapping |
| `services/location-service/src/location_service/routers/processing.py` | Tightened calculate/refresh guards and aligned trigger types |
| `services/location-service/src/location_service/schemas.py` | Forbid extra fields, removed ambiguous request fields, and corrected docs |
| `services/location-service/tests/conftest.py` | Aligned test app/DB setup with validation handler and fresh schema resets |
| `services/location-service/tests/test_audit_findings.py` | Replaced import/export findings with current contract regression checks |
| `services/location-service/tests/test_internal_routes.py` | Added ACTIVE-version and ambiguity coverage for internal resolve |
| `services/location-service/tests/test_mock_pipeline.py` | Added pair row_version setup for pipeline regression |
| `services/location-service/tests/test_pairs_api.py` | Added pair filter/patch/guard coverage for the new contract |
| `services/location-service/tests/test_points_api.py` | Added validation/problem+json coverage for points |
| `services/location-service/tests/test_processing_flow.py` | Removed import/export coverage and added pair row-version approval/discard assertions |

## Deleted
| File | Why |
|------|-----|
| `services/location-service/src/location_service/routers/import_router.py` | Public import endpoint removed from Location Service |
| `services/location-service/src/location_service/routers/export_router.py` | Public export endpoint removed from Location Service |
| `services/location-service/src/location_service/routers/import_export.py` | Import/export router aggregator no longer needed |
| `services/location-service/src/location_service/processing/import_logic.py` | Import processing moved out of Location Service ownership |
| `services/location-service/src/location_service/processing/export_logic.py` | Export processing moved out of Location Service ownership |

---

## Notes
- No file under `services/trip-service/` was modified for TASK-0018.
- The worktree still contains unrelated `trip-service` edits that predated this task and were intentionally left alone.
