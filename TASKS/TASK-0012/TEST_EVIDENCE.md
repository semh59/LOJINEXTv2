# TEST_EVIDENCE.md

## Confidence Level
[ ] High    - automated tests cover key paths, all pass
[ ] Medium  - some automated + manual, no failures found
[x] Low     - manual only, or key paths not covered
[ ] None    - could not run - reason below

---

## Run 1

Command:
```
uv run --directory services/trip-service --extra dev ruff check src tests
```

Output:
```
All checks passed! (full log: TASKS/TASK-0012/logs/ruff_trip.txt)
```

---

## Run 2

Command:
```
uv run --directory services/location-service --extra dev ruff check src tests
```

Output:
```
I001 [*] Import block is un-sorted or un-formatted
 --> src\location_service\routers\export_router.py:3:1
  |
1 |   """Export API endpoints (Section 7.22)."""
2 |
3 | / from fastapi import APIRouter
4 | | from fastapi.responses import StreamingResponse
5 | | from location_service.processing.export_logic import generate_export_csv_stream
  | |_______________________________________________________________________________^
6 |
7 |   router = APIRouter(prefix="/v1/export", tags=["Bulk Operations"])
  |
help: Organize imports

I001 [*] Import block is un-sorted or un-formatted
  --> tests\test_audit_findings.py:7:1
   |
 5 |   """
 6 |
 7 | / import uuid
 8 | | from datetime import UTC, datetime, timedelta
 9 | | from io import BytesIO
10 | | from unittest.mock import AsyncMock, MagicMock, patch
11 | |
12 | | import pytest
13 | | from fastapi import FastAPI
14 | | from fastapi.testclient import TestClient
15 | |
16 | | from location_service.enums import PairStatus, RunStatus
17 | | from location_service.errors import (
18 | |     ProblemDetailError,
19 | |     problem_detail_handler,
20 | | )
21 | | from location_service.models import LocationPoint, ProcessingRun, RoutePair
22 | | from location_service.routers.import_router import router as import_router
23 | | from location_service.routers.pairs import router as pairs_router
24 | | from location_service.routers.points import router as points_router
25 | | from location_service.routers.processing import router as processing_router
   | |___________________________________________________________________________^
   |
help: Organize imports

F401 [*] `io.BytesIO` imported but unused
  --> tests\test_audit_findings.py:9:16
   |
 7 | import uuid
 8 | from datetime import UTC, datetime, timedelta
 9 | from io import BytesIO
   |                ^^^^^^^
10 | from unittest.mock import AsyncMock, MagicMock, patch
   |
help: Remove unused import: `io.BytesIO`

I001 [*] Import block is un-sorted or un-formatted
   --> tests\test_audit_findings.py:76:5
    |
74 |   def test_finding_01_schema_point_update_no_coordinates():
75 |       """PointUpdate schema must NOT have latitude_6dp / longitude_6dp."""
76 | /     from location_service.schemas import PointUpdate
77 | |     import inspect
   | |__________________^
78 |
79 |       fields = PointUpdate.model_fields.keys()
   |
help: Organize imports

F401 [*] `inspect` imported but unused
  --> tests\test_audit_findings.py:77:12
   |
75 |     """PointUpdate schema must NOT have latitude_6dp / longitude_6dp."""
76 |     from location_service.schemas import PointUpdate
77 |     import inspect
   |            ^^^^^^^
78 |
79 |     fields = PointUpdate.model_fields.keys()
   |
help: Remove unused import: `inspect`

F811 [*] Redefinition of unused `BytesIO` from line 9
   --> tests\test_audit_findings.py:471:20
    |
469 | def test_finding_13_import_file_too_large(app_client):
470 |     """POST /v1/import with >20MB file must return 413 with problem+json."""
471 |     from io import BytesIO
    |                    ^^^^^^^ `BytesIO` redefined here
472 |
473 |     # Create a minimal filename but large content
    |
   ::: tests\test_audit_findings.py:9:16
    |
  7 | import uuid
  8 | from datetime import UTC, datetime, timedelta
  9 | from io import BytesIO
    |                ------- previous definition of `BytesIO` here
 10 | from unittest.mock import AsyncMock, MagicMock, patch
    |
help: Remove definition: `BytesIO`

F811 [*] Redefinition of unused `BytesIO` from line 9
   --> tests\test_audit_findings.py:486:20
    |
484 | def test_finding_13_import_wrong_file_type(app_client):
485 |     """POST /v1/import with non-CSV file must return 415 with problem+json."""
486 |     from io import BytesIO
    |                    ^^^^^^^ `BytesIO` redefined here
487 |
488 |     resp = app_client.post(
    |
   ::: tests\test_audit_findings.py:9:16
    |
  7 | import uuid
  8 | from datetime import UTC, datetime, timedelta
  9 | from io import BytesIO
    |                ------- previous definition of `BytesIO` here
 10 | from unittest.mock import AsyncMock, MagicMock, patch
    |
help: Remove definition: `BytesIO`

I001 [*] Import block is un-sorted or un-formatted
   --> tests\test_audit_findings.py:511:5
    |
509 |   def test_finding_14_task_done_callback_removes_task():
510 |       """_task_done_callback must remove finished task from _background_tasks."""
511 | /     from location_service.processing.pipeline import _background_tasks, _task_done_callback
512 | |     import asyncio
    | |__________________^
513 |
514 |       mock_task = MagicMock(spec=asyncio.Task)
    |
help: Organize imports

I001 [*] Import block is un-sorted or un-formatted
  --> tests\test_processing_flow.py:3:1
   |
 1 |   """Integration tests for the Processing Flow (Section 22)."""
 2 |
 3 | / import uuid
 4 | | from unittest.mock import AsyncMock, MagicMock, patch
 5 | |
 6 | | import pytest
 7 | | from location_service.enums import DirectionCode, RunStatus
 8 | | from location_service.models import (
 9 | |     LocationPoint,
10 | |     ProcessingRun,
11 | |     Route,
12 | |     RoutePair,
13 | | )
14 | | from location_service.processing.approval import approve_route_versions
15 | | from location_service.processing.bulk import trigger_bulk_refresh
16 | | from location_service.processing.export_logic import generate_export_csv_stream
17 | | from location_service.processing.import_logic import process_import_csv
18 | | from location_service.processing.pipeline import _process_route_pair
   | |____________________________________________________________________^
   |
help: Organize imports

Found 9 errors.
[*] 9 fixable with the `--fix` option.
(full log: TASKS/TASK-0012/logs/ruff_location.txt)
```

---

## Run 3

Command:
```
uv run --directory services/trip-service --extra dev pytest
```

Output:
```
======================= 39 passed, 2 warnings in 33.93s =======================
(full log: TASKS/TASK-0012/logs/pytest_trip.txt)
```

---

## Run 4

Command:
```
uv run --directory services/location-service --extra dev pytest
```

Output:
```
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: D:\PROJECT\LOJINEXTv2\services\location-service
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=session, asyncio_default_test_loop_scope=function
collected 62 items

tests\test_audit_findings.py .....................                       [ 33%]
tests\test_internal_routes.py ....                                       [ 40%]
tests\test_mock_pipeline.py .                                            [ 41%]
tests\test_pairs_api.py FF                                               [ 45%]
tests\test_points_api.py .F.                                             [ 50%]
tests\test_processing_flow.py .......F..                                 [ 66%]
tests\test_providers.py ....                                             [ 72%]
tests\test_schema.py .                                                   [ 74%]
tests\test_schema_integration.py ..F                                     [ 79%]
tests\test_unit.py ..F..........                                         [100%]

================================== FAILURES ===================================
__________________________ test_create_and_get_pair ___________________________
...
E       TypeError: MemoryView.__init__() missing 1 required positional argument: 'buffer'
src\location_service\domain\codes.py:10: TypeError
___________________________ test_calculate_trigger ____________________________
...
E       TypeError: MemoryView.__init__() missing 1 required positional argument: 'buffer'
src\location_service\domain\codes.py:10: TypeError
______________________________ test_update_point ______________________________
...
E       assert 428 == 200
tests\test_points_api.py:52: AssertionError
_______________________________ test_import_csv _______________________________
...
E       TypeError: MemoryView.__init__() missing 1 required positional argument: 'buffer'
src\location_service\domain\codes.py:10: TypeError
_________________________ test_create_location_point __________________________
...
E   sqlalchemy.exc.IntegrityError: duplicate key value violates unique constraint "location_points_code_key"
tests\test_schema_integration.py:43: IntegrityError
____________________________ test_codes_generation ____________________________
...
E       TypeError: MemoryView.__init__() missing 1 required positional argument: 'buffer'
src\location_service\domain\codes.py:10: TypeError
================== 6 failed, 56 passed, 4 warnings in 12.24s ==================
(full log: TASKS/TASK-0012/logs/pytest_location.txt)
```

---

## Run 5

Command:
```
powershell -ExecutionPolicy Bypass -File TASKS/TASK-0012/scripts/smoke.ps1
```

Output:
```
Starting docker smoke stack...
... docker build + compose up ...
Waiting for trip-service /health...
Running alembic migrations inside service containers...
Seeding location-service database...
Generating JWT tokens in trip-service container...
Manual create trip...
Create empty return...
Telegram full ingest...
Approve Telegram trip...
Telegram fallback ingest...
Excel ingest...
Driver statement...
Hard delete flow...
Smoke completed.
(full log: TASKS/TASK-0012/logs/smoke.txt)
```

Notes:
- One `curl: (52) Empty reply from server` message was observed during the health probe; smoke steps still completed.

---

## Manual Checks

| What | How | Result |
|------|-----|--------|
| File inventory | Enumerated source/test files for trip-service and location-service | 77 files / 12,075 lines reviewed |

---

## Tests That Could Not Run

| Test | Reason | What Enables It |
|------|--------|-----------------|
| None | - | - |
