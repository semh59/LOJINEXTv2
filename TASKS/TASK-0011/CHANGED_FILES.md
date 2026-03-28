# CHANGED_FILES.md

Every file created, modified, or deleted this session.
Small changes count.

---

## Created
| File | Purpose |
|------|---------|
| `TASKS/TASK-0011/BRIEF.md` | Define TASK-0011 scope |
| `TASKS/TASK-0011/PLAN.md` | Lock the implementation plan |
| `TASKS/TASK-0011/STATE.md` | Track progress |
| `TASKS/TASK-0011/CHANGED_FILES.md` | Record file changes |
| `TASKS/TASK-0011/TEST_EVIDENCE.md` | Capture test output |
| `TASKS/TASK-0011/NEXT_AGENT.md` | Leave handoff notes |
| `TASKS/TASK-0011/DONE_CHECKLIST.md` | Task template completeness |

## Modified
| File | What Changed |
|------|-------------|
| `MEMORY/DECISIONS.md` | Recorded the locked bearer-token, route-pair-driven trip contract decision for TASK-0011 |
| `MEMORY/PROJECT_STATE.md` | Moved TASK-0011 to `ready_for_review` and updated the next-step project summary |
| `services/trip-service/.env.example` | Added JWT auth configuration for the new bearer-token contract |
| `services/trip-service/alembic/versions/a1b2c3d4e5f6_trip_service_baseline.py` | Rebaselined the schema around route-pair snapshots, planned windows, source references, and delete audit |
| `services/trip-service/src/trip_service/config.py` | Tuned auth config defaults for the JWT-based public contract |
| `services/trip-service/src/trip_service/dependencies.py` | Added location trip-context client calls and route-resolution helpers for create/enrichment flows |
| `services/trip-service/src/trip_service/errors.py` | Added product-specific problem codes for overlap, review, and delete-audit flows |
| `services/trip-service/src/trip_service/models.py` | Expanded the aggregate with route-pair snapshots, review fields, source references, and delete-audit storage |
| `services/trip-service/src/trip_service/routers/driver_statement.py` | Enforced service-token auth, completed-only output, empty-return filtering, and the 31-day cap |
| `services/trip-service/src/trip_service/routers/removed_endpoints.py` | Added explicit tombstone behavior for the legacy hard-delete path |
| `services/trip-service/src/trip_service/routers/trips.py` | Reworked public/internal APIs for manual create, approve/reject, empty return, Telegram fallback, Excel ingest/export feed, overlap checks, and audited hard delete |
| `services/trip-service/src/trip_service/schemas.py` | Replaced the old request/response contracts with the new route-pair, review, and producer API schemas |
| `services/trip-service/src/trip_service/trip_helpers.py` | Added completeness checks, overlap calculation, trip-context mapping, and delete-audit snapshot helpers |
| `services/trip-service/src/trip_service/workers/enrichment_worker.py` | Treated `EXCEL_IMPORT` records as high-quality import sources during enrichment scoring |
| `services/trip-service/tests/conftest.py` | Rebuilt fixtures around JWT tokens, dynamic time windows, and location/fleet stubs for the new contract |
| `services/trip-service/tests/test_contract.py` | Replaced old endpoint contract coverage with bearer auth, manual-create, hard-delete, and statement-range tests |
| `services/trip-service/tests/test_integration.py` | Added end-to-end coverage for manual create, empty return, approve/reject, Telegram full/fallback ingest, Excel ingest/export feed, overlap blocking, and delete audit |
| `services/trip-service/tests/test_migrations.py` | Asserted the new baseline schema, indexes, and delete-audit table |
| `services/trip-service/tests/test_unit.py` | Added helper-level tests for completeness, planned windows, and overlap behavior |
| `services/trip-service/tests/test_workers.py` | Updated worker tests for retry-ceiling and outbox behavior under the new source model |
| `services/location-service/src/location_service/processing/approval.py` | Marked approved route pairs as `ACTIVE` so trip-context resolution can succeed |
| `services/location-service/src/location_service/routers/internal_routes.py` | Added the new trip-context endpoint while preserving exact-name resolve behavior |
| `services/location-service/src/location_service/schemas.py` | Added the internal trip-context response schema |
| `services/location-service/tests/test_internal_routes.py` | Added coverage for the new trip-context endpoint and active/inactive pair behavior |

## Deleted
| File | Why |
|------|-----|
|      |     |

---

## Notes
`git diff --stat` also shows older TASK-0010 worktree changes that predated TASK-0011. The list above is limited to files touched while implementing TASK-0011.
