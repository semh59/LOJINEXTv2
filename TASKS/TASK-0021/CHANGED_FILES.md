# CHANGED_FILES.md

Every file created or modified for TASK-0021.
Small changes count.

---

## Created
| File | Purpose |
|------|---------|
| `TASKS/TASK-0021/BRIEF.md` | Task definition for the Location frontend-contract work |
| `TASKS/TASK-0021/PLAN.md` | Locked execution plan for TASK-0021 |
| `TASKS/TASK-0021/STATE.md` | Progress and completion state |
| `TASKS/TASK-0021/CHANGED_FILES.md` | File ledger for the task |
| `TASKS/TASK-0021/TEST_EVIDENCE.md` | Verification evidence |
| `TASKS/TASK-0021/NEXT_AGENT.md` | Handoff summary |
| `TASKS/TASK-0021/DONE_CHECKLIST.md` | Completion checklist |
| `services/location-service/src/location_service/query_contracts.py` | Centralized pagination and sort contract helpers |
| `services/location-service/src/location_service/routers/routes_public.py` | Public route-version detail and geometry endpoints |
| `services/location-service/tests/test_contract.py` | Dedicated Location frontend-contract coverage |
| `services/location-service/tests/test_route_versions_api.py` | Public route-version detail and geometry tests |

## Modified
| File | What Changed |
|------|-------------|
| `MEMORY/DECISIONS.md` | Recorded that Location frontend contract work is separate from cleanup and locked public profile codes to `TIR`/`VAN` |
| `MEMORY/PROJECT_STATE.md` | Registered TASK-0021, marked it ready for review, and incremented the next task ID |
| `services/location-service/src/location_service/auth.py` | Added `SUPER_ADMIN`-only dependency for operational public endpoints |
| `services/location-service/src/location_service/main.py` | Wired canonical public processing-run and route read routers |
| `services/location-service/src/location_service/schemas.py` | Expanded public schemas for pairs, processing runs, bulk refresh, and route-version detail/geometry |
| `services/location-service/src/location_service/routers/approval.py` | Returned enriched `PairResponse` payloads after approve/discard |
| `services/location-service/src/location_service/routers/bulk_refresh.py` | Made bulk refresh schema-backed and `SUPER_ADMIN`-only |
| `services/location-service/src/location_service/routers/pairs.py` | Enriched pair payloads with point display fields, profile, route pointers, and frontend list contract support |
| `services/location-service/src/location_service/routers/points.py` | Added canonical `per_page`, deprecated `limit`, validated `sort`, and stable list metadata |
| `services/location-service/src/location_service/routers/processing.py` | Added canonical processing-run endpoints, pair-scoped run history, and `SUPER_ADMIN` force-fail |
| `services/location-service/tests/test_audit_findings.py` | Kept mock audit coverage aligned with the new force-fail auth boundary |
| `services/location-service/tests/test_auth.py` | Covered `SUPER_ADMIN` gating for operational endpoints |
| `services/location-service/tests/test_pairs_api.py` | Covered frontend-complete pair payloads, search/filter/sort, and expanded processing responses |
| `services/location-service/tests/test_points_api.py` | Covered frontend list pagination/sort contract for points |

---

## Notes
- `trip-service` was intentionally not touched in TASK-0021.
- No Alembic migration was added; this task stays strictly on the public contract layer.
- Existing unrelated dirty `trip-service` files remained untouched.
