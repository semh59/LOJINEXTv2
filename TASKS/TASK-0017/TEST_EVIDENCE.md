# TEST_EVIDENCE.md

## Confidence Level
[x] High    - automated tests cover key paths, all pass
[ ] Medium  - some automated + manual, no failures found
[ ] Low     - manual only, or key paths not covered
[ ] None    - could not run - reason below

---

## Run 1

Command:
```
uv run --directory services/trip-service --extra dev pytest
```

Output:
```
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: D:\PROJECT\LOJINEXTv2\services\trip-service
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=session, asyncio_default_test_loop_scope=function
collected 49 items

tests\test_config.py .....                                               [ 10%]
tests\test_contract.py ...........                                       [ 32%]
tests\test_integration.py ...................                            [ 71%]
tests\test_migrations.py .                                               [ 73%]
tests\test_repo_cleanliness.py ...                                       [ 79%]
tests\test_unit.py ....                                                  [ 87%]
tests\test_workers.py ......                                             [100%]

============================== warnings summary ===============================
tests/test_config.py::test_validate_prod_rejects_default_jwt_secret
tests/test_migrations.py::test_alembic_upgrade_head_on_empty_postgres
  D:\PROJECT\LOJINEXTv2\services\trip-service\.venv\Lib\site-packages\alembic\config.py:612: DeprecationWarning: No path_separator found in configuration; falling back to legacy splitting on spaces, commas, and colons for prepend_sys_path.  Consider adding path_separator=os to Alembic config.
    util.warn_deprecated(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 49 passed, 2 warnings in 40.48s =======================

```

---

## Run 2

Command:
```
powershell -ExecutionPolicy Bypass -File TASKS/TASK-0012/scripts/smoke.ps1
```

Output:
```
Starting docker smoke stack...
 Image task-0012-fleet-stub Building 
 Image task-0012-telegram-stub Building 
 Image task-0012-excel-stub Building 
 Image task-0012-trip-service Building 
 Image task-0012-location-service Building 
#1 [internal] load local bake definitions
#1 reading from stdin 2.63kB 0.0s done
#1 DONE 0.0s

#2 [telegram-stub internal] load build definition from Dockerfile
#2 transferring dockerfile: 360B 0.0s done
#2 DONE 0.0s

#3 [trip-service internal] load build definition from Dockerfile
#3 transferring dockerfile: 603B done
#3 DONE 0.0s

#4 [location-service internal] load build definition from Dockerfile
#4 transferring dockerfile: 608B done
#4 DONE 0.0s

#5 [trip-service internal] load metadata for docker.io/library/python:3.12-slim
#5 DONE 0.6s

#6 [trip-service internal] load .dockerignore
#6 transferring context: 123B done
#6 DONE 0.0s

#7 [location-service internal] load .dockerignore
#7 transferring context: 2B done
#7 DONE 0.0s

#8 [telegram-stub internal] load .dockerignore
#8 transferring context: 2B done
#8 DONE 0.0s

#9 [excel-stub internal] load build context
#9 transferring context: 63B done
#9 DONE 0.0s

#10 [excel-stub 1/9] FROM docker.io/library/python:3.12-slim@sha256:3d5ed973e45820f5ba5e46bd065bd88b3a504ff0724d85980dcd05eab361fcf4
#10 resolve docker.io/library/python:3.12-slim@sha256:3d5ed973e45820f5ba5e46bd065bd88b3a504ff0724d85980dcd05eab361fcf4 0.0s done
#10 DONE 0.1s

#11 [trip-service internal] load build context
#11 transferring context: 4.68kB 0.0s done
#11 DONE 0.0s

#12 [location-service internal] load build context
#12 transferring context: 5.83kB 0.0s done
#12 DONE 0.0s

#13 [fleet-stub 3/5] COPY requirements.txt ./
#13 CACHED

#14 [fleet-stub 4/5] RUN python -m pip install --upgrade pip     && python -m pip install --no-cache-dir -r requirements.txt
#14 CACHED

#15 [fleet-stub 2/5] WORKDIR /app
#15 CACHED

#16 [trip-service 8/9] COPY src ./src
#16 CACHED

#17 [trip-service 6/9] COPY alembic.ini ./
#17 CACHED

#18 [trip-service 7/9] COPY alembic ./alembic
#18 CACHED

#19 [trip-service 5/9] COPY pyproject.toml ./
#19 CACHED

#20 [trip-service 9/9] RUN python -m pip install --upgrade pip     && python -m pip install --no-cache-dir .
#20 CACHED

#21 [telegram-stub 5/5] COPY app.py ./
#21 CACHED

#22 [location-service 5/9] COPY pyproject.toml ./
#22 CACHED

#23 [location-service 7/9] COPY alembic ./alembic
#23 CACHED

#24 [location-service 8/9] COPY src ./src
#24 CACHED

#25 [location-service 3/9] WORKDIR /app
#25 CACHED

#26 [location-service 4/9] RUN useradd --create-home --shell /usr/sbin/nologin appuser
#26 CACHED

#27 [location-service 2/9] RUN apt-get update     && apt-get install -y --no-install-recommends tzdata ca-certificates     && rm -rf /var/lib/apt/lists/*
#27 CACHED

#28 [location-service 6/9] COPY alembic.ini ./
#28 CACHED

#29 [location-service 9/9] RUN python -m pip install --upgrade pip     && python -m pip install --no-cache-dir .
#29 CACHED

#30 [trip-service] exporting to image
#30 exporting layers done
#30 exporting manifest sha256:b92ec2a6cb53aefbd344a4309bf86ae41427e5b3b7252fbd9416ea15d9005dc9 0.0s done
#30 exporting config sha256:e64dfbbe419c5f04d1a3330e349e05c935c423a161c2e8bfd8977608a972d22e 0.0s done
#30 exporting attestation manifest sha256:07126f8a46cbc0557c6ab13873fbaeb3ab5d0007dd31ce155669d527dd407902
#30 exporting attestation manifest sha256:07126f8a46cbc0557c6ab13873fbaeb3ab5d0007dd31ce155669d527dd407902 0.1s done
#30 exporting manifest list sha256:25b1f370b80872cbe7a19aca4b5af05615fa92c541cbc9287c78097c587de288
#30 ...

#31 [fleet-stub] exporting to image
#31 exporting layers done
#31 exporting manifest sha256:d4548a5b95762d17a4a9d5a3cd3f8fd17b89948fe13ba969ef8ba92f6523d39b done
#31 exporting config sha256:3f70b4e45be87f67f1184aae29957b2530bf7b9fae8fc7a215ae341e5b0ddd7c done
#31 exporting attestation manifest sha256:bcb235c02404d6c46a75fa3778aa7d11627eed6715277b35c5cd59bf5c6918c1 0.1s done
#31 exporting manifest list sha256:3fcef9a8584b9b3dc7b941d273cf5a4b7e8fd22eb1af80f79120537fd3e1c5ef 0.1s done
#31 naming to docker.io/library/task-0012-fleet-stub:latest 0.0s done
#31 unpacking to docker.io/library/task-0012-fleet-stub:latest 0.0s done
#31 DONE 0.3s

#32 [telegram-stub] exporting to image
#32 exporting layers done
#32 exporting manifest sha256:a970529cca435ee9e1df845488de70ef2ea84a2a82588cfac7d97472f0c11de9 done
#32 exporting config sha256:d7ce34f903645f8e968fd46f46d807fab1d49910ef255fe346edde52d45d349e 0.0s done
#32 exporting attestation manifest sha256:83626c08b91d33e5ffb65141e1c20221556d36029b27be490e2700bd64300e8c 0.1s done
#32 exporting manifest list sha256:2b476a2a6fc0e62d5dc61f9c779562c869eb0474496a92717b1bc9bde89c9427 0.1s done
#32 naming to docker.io/library/task-0012-telegram-stub:latest 0.0s done
#32 unpacking to docker.io/library/task-0012-telegram-stub:latest 0.0s done
#32 DONE 0.4s

#30 [trip-service] exporting to image
#30 exporting manifest list sha256:25b1f370b80872cbe7a19aca4b5af05615fa92c541cbc9287c78097c587de288 0.0s done
#30 naming to docker.io/library/task-0012-trip-service:latest done
#30 unpacking to docker.io/library/task-0012-trip-service:latest 0.1s done
#30 DONE 0.4s

#33 [excel-stub] exporting to image
#33 exporting layers done
#33 exporting manifest sha256:95e010888548fd4f7a4bb7c6ce40af79aa07f877f885e020001b2c6787041926 done
#33 exporting config sha256:8411f55a43d22a5865835a1bcb262bb0f103e8b9568d649e9a9f600742c958bb 0.0s done
#33 exporting attestation manifest sha256:318ab05dac731e8a2ed90db7f89369be09be720d37a87f10654be9df769c7019 0.1s done
#33 exporting manifest list sha256:9f486a7ff4e91d9ebccb5f73d9ac7a30851c28a23b6e32aacca3e1d9e1514f72 0.1s done
#33 naming to docker.io/library/task-0012-excel-stub:latest 0.0s done
#33 unpacking to docker.io/library/task-0012-excel-stub:latest 0.0s done
#33 DONE 0.4s

#34 [location-service] exporting to image
#34 exporting layers done
#34 exporting manifest sha256:cc1ab6650b60d3a2822e66313b124a562f8e97f4ba65741b162c5ac01b36f525 0.0s done
#34 exporting config sha256:325dab3c2ebc1c3820481b0075630c47c3c63fa9c3744163a92dba7cdc1c2165 0.0s done
#34 exporting attestation manifest sha256:f5aee671589f607c8a1e5d05c7e7ba00c0ec740a4d787b8946fd9d783cc753b2 0.1s done
#34 exporting manifest list sha256:d806a3caef9427ec0c4c5f96c11fe1debfb48f4e933a22239378acafa827fcbc 0.0s done
#34 naming to docker.io/library/task-0012-location-service:latest done
#34 unpacking to docker.io/library/task-0012-location-service:latest 0.1s done
#34 DONE 0.4s

#35 [telegram-stub] resolving provenance for metadata file
#35 DONE 0.1s

#36 [trip-service] resolving provenance for metadata file
#36 DONE 0.0s

#37 [location-service] resolving provenance for metadata file
#37 DONE 0.1s

#38 [fleet-stub] resolving provenance for metadata file
#38 DONE 0.1s

#39 [excel-stub] resolving provenance for metadata file
#39 DONE 0.1s
 Image task-0012-telegram-stub Built 
 Image task-0012-fleet-stub Built 
 Image task-0012-location-service Built 
 Image task-0012-trip-service Built 
 Image task-0012-excel-stub Built 
 Container task-0012-postgres-1 Running 
 Container task-0012-excel-stub-1 Recreate 
 Container task-0012-location-service-1 Recreate 
 Container task-0012-redpanda-1 Running 
 Container task-0012-telegram-stub-1 Recreate 
 Container task-0012-fleet-stub-1 Recreate 
 Container task-0012-fleet-stub-1 Recreated 
 Container task-0012-telegram-stub-1 Recreated 
 Container task-0012-excel-stub-1 Recreated 
 Container task-0012-location-service-1 Recreated 
 Container task-0012-trip-service-1 Recreate 
 Container task-0012-trip-service-1 Recreated 
 Container task-0012-telegram-stub-1 Starting 
 Container task-0012-fleet-stub-1 Starting 
 Container task-0012-excel-stub-1 Starting 
 Container task-0012-postgres-1 Waiting 
 Container task-0012-telegram-stub-1 Started 
 Container task-0012-excel-stub-1 Started 
 Container task-0012-postgres-1 Healthy 
 Container task-0012-location-service-1 Starting 
 Container task-0012-fleet-stub-1 Started 
 Container task-0012-location-service-1 Started 
 Container task-0012-postgres-1 Waiting 
 Container task-0012-postgres-1 Healthy 
 Container task-0012-trip-service-1 Starting 
 Container task-0012-trip-service-1 Started 
Waiting for trip-service /health...
Running alembic migrations inside service containers...
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
Seeding location-service database...
You are now connected to database "location_service" as user "postgres".
INSERT 0 0
INSERT 0 0
INSERT 0 0
UPDATE 1
INSERT 0 0
Generating JWT tokens in trip-service container...
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbi0xIiwicm9sZSI6IkFETUlOIn0.M7ha8kBxrxf0hbiLu6-3DM5xwwggyGMg5aS08DgfDT4
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzdXBlci0xIiwicm9sZSI6IlNVUEVSX0FETUlOIn0.2wdBTuYet1to9EdH-iqzVuxU9TRBpRNu3Br_SAXhEjA
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZWxlZ3JhbS1zZXJ2aWNlIiwicm9sZSI6IlNFUlZJQ0UiLCJzZXJ2aWNlIjoidGVsZWdyYW0tc2VydmljZSJ9.xokdUZQUKNhs_2ygCTjjmSPClZdjLBT7X3uKiK3RJyo
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJleGNlbC1zZXJ2aWNlIiwicm9sZSI6IlNFUlZJQ0UiLCJzZXJ2aWNlIjoiZXhjZWwtc2VydmljZSJ9.Ja9vxu-gFfD_dWzc_hQof579pm0SwNEWuk9U0ajT89E
Manual create trip...
Create empty return...
Telegram full ingest...
Approve Telegram trip...
Telegram fallback ingest...
Excel ingest...
Driver statement...
Hard delete flow...
Smoke completed.

```
