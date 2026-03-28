# TEST_EVIDENCE.md

## Confidence Level
[ ] High    - automated tests cover key paths, all pass
[x] Medium  - some automated + manual, no failures found
[ ] Low     - manual only, or key paths not covered
[ ] None    - could not run - reason below

---

## Run 1

Command:
`
uv run --directory services/trip-service --extra dev ruff check src tests
`

Output:
`
All checks passed!

`

---

## Run 2

Command:
`
uv run --directory services/location-service --extra dev ruff check src tests
`

Output:
`
All checks passed!

`

---

## Run 3

Command:
`
uv run --directory services/trip-service --extra dev pytest
`

Output:
`
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: D:\PROJECT\LOJINEXTv2\services\trip-service
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=session, asyncio_default_test_loop_scope=function
collected 39 items

tests\test_contract.py ...........                                       [ 28%]
tests\test_integration.py ................                               [ 69%]
tests\test_migrations.py .                                               [ 71%]
tests\test_repo_cleanliness.py ...                                       [ 79%]
tests\test_unit.py ....                                                  [ 89%]
tests\test_workers.py ....                                               [100%]

============================== warnings summary ===============================
tests/test_contract.py::test_public_endpoints_require_bearer_auth
tests/test_migrations.py::test_alembic_upgrade_head_on_empty_postgres
  D:\PROJECT\LOJINEXTv2\services\trip-service\.venv\Lib\site-packages\alembic\config.py:612: DeprecationWarning: No path_separator found in configuration; falling back to legacy splitting on spaces, commas, and colons for prepend_sys_path.  Consider adding path_separator=os to Alembic config.
    util.warn_deprecated(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 39 passed, 2 warnings in 33.22s =======================

`

---

## Run 4

Command:
`
uv run --directory services/location-service --extra dev pytest
`

Output:
`
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
tests\test_pairs_api.py ..                                               [ 45%]
tests\test_points_api.py ...                                             [ 50%]
tests\test_processing_flow.py ..........                                 [ 66%]
tests\test_providers.py ....                                             [ 72%]
tests\test_schema.py .                                                   [ 74%]
tests\test_schema_integration.py ...                                     [ 79%]
tests\test_unit.py .............                                         [100%]

============================= 62 passed in 9.79s ==============================

`

---

## Run 5

Command:
`
powershell -ExecutionPolicy Bypass -File TASKS/TASK-0012/scripts/smoke.ps1
`

Output:
`
Starting docker smoke stack...
powershell :  Image task-0012-location-service Building 
At line:2 char:1
+ powershell -ExecutionPolicy Bypass -File TASKS/TASK-0012/scripts/smok ...
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: ( Image task-001...rvice Building :String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
 Image task-0012-fleet-stub Building 
 Image task-0012-telegram-stub Building 
 Image task-0012-excel-stub Building 
 Image task-0012-trip-service Building 
#1 [internal] load local bake definitions
#1 reading from stdin 2.63kB 0.1s done
#1 DONE 0.1s

#2 [trip-service internal] load build definition from Dockerfile
#2 transferring dockerfile: 603B 0.0s done
#2 DONE 0.0s

#3 [excel-stub internal] load build definition from Dockerfile
#3 transferring dockerfile: 360B 0.0s done
#3 DONE 0.1s

#4 [location-service internal] load build definition from Dockerfile
#4 transferring dockerfile: 608B 0.0s done
#4 DONE 0.1s

#5 [location-service internal] load metadata for docker.io/library/python:3.12-slim
#5 ...

#6 [auth] library/python:pull token for registry-1.docker.io
#6 DONE 0.0s

#5 [location-service internal] load metadata for docker.io/library/python:3.12-slim
#5 DONE 1.1s

#7 [excel-stub internal] load .dockerignore
#7 transferring context: 2B done
#7 DONE 0.0s

#8 [location-service internal] load .dockerignore
#8 transferring context: 2B done
#8 DONE 0.0s

#9 [trip-service internal] load .dockerignore
#9 transferring context: 123B done
#9 DONE 0.0s

#10 [fleet-stub internal] load build context
#10 transferring context: 63B done
#10 DONE 0.0s

#11 [excel-stub 1/5] FROM docker.io/library/python:3.12-slim@sha256:3d5ed973e45820f5ba5e46bd065bd88b3a504ff0724d85980dcd05eab361fcf4
#11 resolve docker.io/library/python:3.12-slim@sha256:3d5ed973e45820f5ba5e46bd065bd88b3a504ff0724d85980dcd05eab361fcf4 0.0s done
#11 DONE 0.0s

#12 [trip-service internal] load build context
#12 transferring context: 4.68kB 0.0s done
#12 DONE 0.0s

#13 [fleet-stub 4/5] RUN python -m pip install --upgrade pip     && python -m pip install --no-cache-dir -r requirements.txt
#13 CACHED

#14 [fleet-stub 2/5] WORKDIR /app
#14 CACHED

#15 [fleet-stub 3/5] COPY requirements.txt ./
#15 CACHED

#16 [excel-stub 5/5] COPY app.py ./
#16 CACHED

#17 [location-service internal] load build context
#17 transferring context: 8.75kB 0.0s done
#17 DONE 0.1s

#18 [trip-service 5/9] COPY pyproject.toml ./
#18 CACHED

#19 [trip-service 8/9] COPY src ./src
#19 CACHED

#20 [trip-service 6/9] COPY alembic.ini ./
#20 CACHED

#21 [trip-service 7/9] COPY alembic ./alembic
#21 CACHED

#22 [trip-service 9/9] RUN python -m pip install --upgrade pip     && python -m pip install --no-cache-dir .
#22 CACHED

#23 [location-service 2/9] RUN apt-get update     && apt-get install -y --no-install-recommends tzdata ca-certificates     && rm -rf /var/lib/apt/lists/*
#23 CACHED

#24 [location-service 6/9] COPY alembic.ini ./
#24 CACHED

#25 [location-service 5/9] COPY pyproject.toml ./
#25 CACHED

#26 [location-service 3/9] WORKDIR /app
#26 CACHED

#27 [location-service 4/9] RUN useradd --create-home --shell /usr/sbin/nologin appuser
#27 CACHED

#28 [location-service 7/9] COPY alembic ./alembic
#28 CACHED

#29 [trip-service] exporting to image
#29 exporting layers 0.0s done
#29 exporting manifest sha256:6e98f2df6b07b47442bec011062d674ad65d92c53e4768877e8816e098bb1d38 0.0s done
#29 exporting config sha256:8ca30ca62d033850ef0f1a651f460af767f5fcdddd43077d04503bd1e931894d 0.0s done
#29 exporting attestation manifest sha256:1faa64864194274f68db5183a8c7e13881d83098533b6d71b02b6472a56028f1
#29 ...

#30 [location-service 8/9] COPY src ./src
#30 DONE 0.3s

#31 [telegram-stub] exporting to image
#31 exporting layers 0.0s done
#31 exporting manifest sha256:a970529cca435ee9e1df845488de70ef2ea84a2a82588cfac7d97472f0c11de9 0.0s done
#31 exporting config sha256:d7ce34f903645f8e968fd46f46d807fab1d49910ef255fe346edde52d45d349e 0.0s done
#31 exporting attestation manifest sha256:4360436db114d18a816e9d71fef2a232199455a331883fe3d08509fe3d9f6440 0.2s done
#31 exporting manifest list sha256:25dc49daa60359a3fc5984055eb0354fa1655893dac6ddd9680d0e3b780f3e51 0.1s done
#31 naming to docker.io/library/task-0012-telegram-stub:latest 0.0s done
#31 unpacking to docker.io/library/task-0012-telegram-stub:latest 0.0s done
#31 DONE 0.5s

#29 [trip-service] exporting to image
#29 exporting attestation manifest sha256:1faa64864194274f68db5183a8c7e13881d83098533b6d71b02b6472a56028f1 0.1s done
#29 exporting manifest list sha256:bbd06a99fcd44708d70dfde924c076d59288bf34a922e06ab26c5be17a6b19c0 0.0s done
#29 naming to docker.io/library/task-0012-trip-service:latest 0.0s done
#29 unpacking to docker.io/library/task-0012-trip-service:latest
#29 unpacking to docker.io/library/task-0012-trip-service:latest 0.1s done
#29 DONE 0.5s

#32 [fleet-stub] exporting to image
#32 exporting layers 0.0s done
#32 exporting manifest sha256:d4548a5b95762d17a4a9d5a3cd3f8fd17b89948fe13ba969ef8ba92f6523d39b 0.0s done
#32 exporting config sha256:3f70b4e45be87f67f1184aae29957b2530bf7b9fae8fc7a215ae341e5b0ddd7c 0.0s done
#32 exporting attestation manifest sha256:4d0fdccf69800c637d3c74a1198323532a8d83f74f78ec87d17e84549c7e36f0 0.2s done
#32 exporting manifest list sha256:8bf467c081468364a3bed878bf4e37009eee07dd153c72d14a1c4eab5d91880d 0.1s done
#32 naming to docker.io/library/task-0012-fleet-stub:latest 0.0s done
#32 unpacking to docker.io/library/task-0012-fleet-stub:latest 0.0s done
#32 DONE 0.5s

#33 [excel-stub] exporting to image
#33 exporting layers 0.0s done
#33 exporting manifest sha256:95e010888548fd4f7a4bb7c6ce40af79aa07f877f885e020001b2c6787041926 0.0s done
#33 exporting config sha256:8411f55a43d22a5865835a1bcb262bb0f103e8b9568d649e9a9f600742c958bb 0.0s done
#33 exporting attestation manifest sha256:a44e9a16fe1e919871a6794ea90ef5602192fcd6868682e35d9ed84504e43b40 0.2s done
#33 exporting manifest list sha256:be9ab259c4b35eb4944d44721e5ad8bda39fb0a4fe9c6a16f3c9c33fac6c2814 0.1s done
#33 naming to docker.io/library/task-0012-excel-stub:latest 0.0s done
#33 unpacking to docker.io/library/task-0012-excel-stub:latest 0.0s done
#33 DONE 0.6s

#34 [location-service 9/9] RUN python -m pip install --upgrade pip     && python -m pip install --no-cache-dir .
#34 ...

#35 [fleet-stub] resolving provenance for metadata file
#35 DONE 0.0s

#36 [telegram-stub] resolving provenance for metadata file
#36 DONE 0.0s

#37 [excel-stub] resolving provenance for metadata file
#37 DONE 0.0s

#38 [trip-service] resolving provenance for metadata file
#38 DONE 0.0s

#34 [location-service 9/9] RUN python -m pip install --upgrade pip     && python -m pip install --no-cache-dir .
#34 2.542 Requirement already satisfied: pip in /usr/local/lib/python3.12/site-packages (25.0.1)
#34 2.851 Collecting pip
#34 3.103   Downloading pip-26.0.1-py3-none-any.whl.metadata (4.7 kB)
#34 3.188 Downloading pip-26.0.1-py3-none-any.whl (1.8 MB)
#34 3.780    ???????????????????????????????????????? 1.8/1.8 MB 3.9 MB/s eta 0:00:00
#34 3.801 Installing collected packages: pip
#34 3.802   Attempting uninstall: pip
#34 3.806     Found existing installation: pip 25.0.1
#34 3.869     Uninstalling pip-25.0.1:
#34 4.218       Successfully uninstalled pip-25.0.1
#34 5.346 Successfully installed pip-26.0.1
#34 5.346 WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager, possibly rendering your system unusable. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv. Use the --root-user-action option if you know what you are doing and want to suppress this warning.
#34 6.576 Processing ./.
#34 6.581   Installing build dependencies: started
#34 9.091   Installing build dependencies: finished with status 'done'
#34 9.093   Getting requirements to build wheel: started
#34 10.08   Getting requirements to build wheel: finished with status 'done'
#34 10.08   Preparing metadata (pyproject.toml): started
#34 11.02   Preparing metadata (pyproject.toml): finished with status 'done'
#34 11.39 Collecting fastapi>=0.115.0 (from location-service==0.1.0)
#34 11.62   Downloading fastapi-0.135.2-py3-none-any.whl.metadata (28 kB)
#34 11.74 Collecting uvicorn>=0.30.0 (from uvicorn[standard]>=0.30.0->location-service==0.1.0)
#34 11.81   Downloading uvicorn-0.42.0-py3-none-any.whl.metadata (6.7 kB)
#34 12.39 Collecting sqlalchemy>=2.0.30 (from sqlalchemy[asyncio]>=2.0.30->location-service==0.1.0)
#34 12.46   Downloading sqlalchemy-2.0.48-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (9.5 kB)
#34 12.61 Collecting asyncpg>=0.30.0 (from location-service==0.1.0)
#34 12.68   Downloading asyncpg-0.31.0-cp312-cp312-manylinux_2_28_x86_64.whl.metadata (4.4 kB)
#34 12.77 Collecting alembic>=1.13.0 (from location-service==0.1.0)
#34 12.84   Downloading alembic-1.18.4-py3-none-any.whl.metadata (7.2 kB)
#34 13.05 Collecting pydantic>=2.7.0 (from location-service==0.1.0)
#34 13.12   Downloading pydantic-2.12.5-py3-none-any.whl.metadata (90 kB)
#34 13.29 Collecting pydantic-settings>=2.3.0 (from location-service==0.1.0)
#34 13.36   Downloading pydantic_settings-2.13.1-py3-none-any.whl.metadata (3.4 kB)
#34 13.44 Collecting python-ulid>=3.0.0 (from location-service==0.1.0)
#34 13.51   Downloading python_ulid-3.1.0-py3-none-any.whl.metadata (5.8 kB)
#34 13.59 Collecting httpx>=0.27.0 (from location-service==0.1.0)
#34 13.66   Downloading httpx-0.28.1-py3-none-any.whl.metadata (7.1 kB)
#34 13.73 Collecting openpyxl>=3.1.0 (from location-service==0.1.0)
#34 13.81   Downloading openpyxl-3.1.5-py2.py3-none-any.whl.metadata (2.5 kB)
#34 13.88 Collecting python-multipart>=0.0.9 (from location-service==0.1.0)
#34 13.95   Downloading python_multipart-0.0.22-py3-none-any.whl.metadata (1.8 kB)
#34 14.02 Collecting prometheus-client>=0.20.0 (from location-service==0.1.0)
#34 14.09   Downloading prometheus_client-0.24.1-py3-none-any.whl.metadata (2.1 kB)
#34 14.40 Collecting Pillow>=10.0.0 (from location-service==0.1.0)
#34 14.47   Downloading pillow-12.1.1-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl.metadata (8.8 kB)
#34 14.65 Collecting canonicaljson>=2.0.0 (from location-service==0.1.0)
#34 14.71   Downloading canonicaljson-2.0.0-py3-none-any.whl.metadata (2.6 kB)
#34 14.89 Collecting ulid-py>=1.1.0 (from location-service==0.1.0)
#34 14.97   Downloading ulid_py-1.1.0-py2.py3-none-any.whl.metadata (9.8 kB)
#34 15.06 Collecting Mako (from alembic>=1.13.0->location-service==0.1.0)
#34 15.13   Downloading mako-1.3.10-py3-none-any.whl.metadata (2.9 kB)
#34 15.20 Collecting typing-extensions>=4.12 (from alembic>=1.13.0->location-service==0.1.0)
#34 15.28   Downloading typing_extensions-4.15.0-py3-none-any.whl.metadata (3.3 kB)
#34 15.36 Collecting starlette>=0.46.0 (from fastapi>=0.115.0->location-service==0.1.0)
#34 15.44   Downloading starlette-1.0.0-py3-none-any.whl.metadata (6.3 kB)
#34 15.51 Collecting typing-inspection>=0.4.2 (from fastapi>=0.115.0->location-service==0.1.0)
#34 15.58   Downloading typing_inspection-0.4.2-py3-none-any.whl.metadata (2.6 kB)
#34 15.66 Collecting annotated-doc>=0.0.2 (from fastapi>=0.115.0->location-service==0.1.0)
#34 15.74   Downloading annotated_doc-0.0.4-py3-none-any.whl.metadata (6.6 kB)
#34 15.82 Collecting anyio (from httpx>=0.27.0->location-service==0.1.0)
#34 15.89   Downloading anyio-4.13.0-py3-none-any.whl.metadata (4.5 kB)
#34 15.97 Collecting certifi (from httpx>=0.27.0->location-service==0.1.0)
#34 16.04   Downloading certifi-2026.2.25-py3-none-any.whl.metadata (2.5 kB)
#34 16.12 Collecting httpcore==1.* (from httpx>=0.27.0->location-service==0.1.0)
#34 16.20   Downloading httpcore-1.0.9-py3-none-any.whl.metadata (21 kB)
#34 16.27 Collecting idna (from httpx>=0.27.0->location-service==0.1.0)
#34 16.34   Downloading idna-3.11-py3-none-any.whl.metadata (8.4 kB)
#34 16.42 Collecting h11>=0.16 (from httpcore==1.*->httpx>=0.27.0->location-service==0.1.0)
#34 16.52   Downloading h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
#34 16.60 Collecting et-xmlfile (from openpyxl>=3.1.0->location-service==0.1.0)
#34 16.67   Downloading et_xmlfile-2.0.0-py3-none-any.whl.metadata (2.7 kB)
#34 16.75 Collecting annotated-types>=0.6.0 (from pydantic>=2.7.0->location-service==0.1.0)
#34 16.82   Downloading annotated_types-0.7.0-py3-none-any.whl.metadata (15 kB)
#34 18.01 Collecting pydantic-core==2.41.5 (from pydantic>=2.7.0->location-service==0.1.0)
#34 18.08   Downloading pydantic_core-2.41.5-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (7.3 kB)
#34 18.16 Collecting python-dotenv>=0.21.0 (from pydantic-settings>=2.3.0->location-service==0.1.0)
#34 18.25   Downloading python_dotenv-1.2.2-py3-none-any.whl.metadata (27 kB)
#34 18.56 Collecting greenlet>=1 (from sqlalchemy>=2.0.30->sqlalchemy[asyncio]>=2.0.30->location-service==0.1.0)
#34 18.63   Downloading greenlet-3.3.2-cp312-cp312-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl.metadata (3.7 kB)
#34 18.73 Collecting click>=7.0 (from uvicorn>=0.30.0->uvicorn[standard]>=0.30.0->location-service==0.1.0)
#34 18.80   Downloading click-8.3.1-py3-none-any.whl.metadata (2.6 kB)
#34 18.89 Collecting httptools>=0.6.3 (from uvicorn[standard]>=0.30.0->location-service==0.1.0)
#34 18.97   Downloading httptools-0.7.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (3.5 kB)
#34 19.07 Collecting pyyaml>=5.1 (from uvicorn[standard]>=0.30.0->location-service==0.1.0)
#34 19.14   Downloading pyyaml-6.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (2.4 kB)
#34 19.27 Collecting uvloop>=0.15.1 (from uvicorn[standard]>=0.30.0->location-service==0.1.0)
#34 19.34   Downloading uvloop-0.22.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (4.9 kB)
#34 19.51 Collecting watchfiles>=0.20 (from uvicorn[standard]>=0.30.0->location-service==0.1.0)
#34 19.58   Downloading watchfiles-1.1.1-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (4.9 kB)
#34 19.76 Collecting websockets>=10.4 (from uvicorn[standard]>=0.30.0->location-service==0.1.0)
#34 19.85   Downloading websockets-16.0-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (6.8 kB)
#34 20.00 Collecting MarkupSafe>=0.9.2 (from Mako->alembic>=1.13.0->location-service==0.1.0)
#34 20.08   Downloading markupsafe-3.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (2.7 kB)
#34 20.15 Downloading alembic-1.18.4-py3-none-any.whl (263 kB)
#34 20.32 Downloading asyncpg-0.31.0-cp312-cp312-manylinux_2_28_x86_64.whl (3.5 MB)
#34 20.80    ???????????????????????????????????????? 3.5/3.5 MB 8.1 MB/s  0:00:00
#34 20.87 Downloading canonicaljson-2.0.0-py3-none-any.whl (7.9 kB)
#34 20.94 Downloading fastapi-0.135.2-py3-none-any.whl (117 kB)
#34 21.01 Downloading annotated_doc-0.0.4-py3-none-any.whl (5.3 kB)
#34 21.09 Downloading httpx-0.28.1-py3-none-any.whl (73 kB)
#34 21.16 Downloading httpcore-1.0.9-py3-none-any.whl (78 kB)
#34 21.24 Downloading h11-0.16.0-py3-none-any.whl (37 kB)
#34 21.32 Downloading openpyxl-3.1.5-py2.py3-none-any.whl (250 kB)
#34 21.40 Downloading pillow-12.1.1-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl (7.0 MB)
#34 21.91    ???????????????????????????????????????? 7.0/7.0 MB 13.9 MB/s  0:00:00
#34 21.98 Downloading prometheus_client-0.24.1-py3-none-any.whl (64 kB)
#34 22.06 Downloading pydantic-2.12.5-py3-none-any.whl (463 kB)
#34 22.17 Downloading pydantic_core-2.41.5-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.1 MB)
#34 22.35    ???????????????????????????????????????? 2.1/2.1 MB 10.7 MB/s  0:00:00
#34 22.45 Downloading annotated_types-0.7.0-py3-none-any.whl (13 kB)
#34 22.52 Downloading pydantic_settings-2.13.1-py3-none-any.whl (58 kB)
#34 22.61 Downloading python_dotenv-1.2.2-py3-none-any.whl (22 kB)
#34 22.69 Downloading python_multipart-0.0.22-py3-none-any.whl (24 kB)
#34 22.76 Downloading python_ulid-3.1.0-py3-none-any.whl (11 kB)
#34 22.83 Downloading sqlalchemy-2.0.48-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (3.3 MB)
#34 23.12    ???????????????????????????????????????? 3.3/3.3 MB 11.5 MB/s  0:00:00
#34 23.20 Downloading greenlet-3.3.2-cp312-cp312-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl (613 kB)
#34 23.24    ???????????????????????????????????????? 613.9/613.9 kB 16.1 MB/s  0:00:00
#34 23.31 Downloading starlette-1.0.0-py3-none-any.whl (72 kB)
#34 23.38 Downloading anyio-4.13.0-py3-none-any.whl (114 kB)
#34 23.47 Downloading idna-3.11-py3-none-any.whl (71 kB)
#34 23.54 Downloading typing_extensions-4.15.0-py3-none-any.whl (44 kB)
#34 23.62 Downloading typing_inspection-0.4.2-py3-none-any.whl (14 kB)
#34 23.68 Downloading ulid_py-1.1.0-py2.py3-none-any.whl (25 kB)
#34 23.76 Downloading uvicorn-0.42.0-py3-none-any.whl (68 kB)
#34 23.84 Downloading click-8.3.1-py3-none-any.whl (108 kB)
#34 23.93 Downloading httptools-0.7.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (517 kB)
#34 24.03 Downloading pyyaml-6.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (807 kB)
#34 24.07    ???????????????????????????????????????? 807.9/807.9 kB 16.4 MB/s  0:00:00
#34 24.17 Downloading uvloop-0.22.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (4.4 MB)
#34 24.51    ???????????????????????????????????????? 4.4/4.4 MB 12.9 MB/s  0:00:00
#34 24.60 Downloading watchfiles-1.1.1-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (456 kB)
#34 24.70 Downloading websockets-16.0-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (184 kB)
#34 24.79 Downloading certifi-2026.2.25-py3-none-any.whl (153 kB)
#34 24.87 Downloading et_xmlfile-2.0.0-py3-none-any.whl (18 kB)
#34 24.94 Downloading mako-1.3.10-py3-none-any.whl (78 kB)
#34 25.01 Downloading markupsafe-3.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (22 kB)
#34 25.07 Building wheels for collected packages: location-service
#34 25.07   Building wheel for location-service (pyproject.toml): started
#34 26.12   Building wheel for location-service (pyproject.toml): finished with status 'done'
#34 26.13   Created wheel for location-service: filename=location_service-0.1.0-py3-none-any.whl size=48701 sha256=a9d27391c5342e0ad4437bf0769293fc64e391467880f7c37d9169efa502f6de
#34 26.13   Stored in directory: /tmp/pip-ephem-wheel-cache-8909nb0t/wheels/54/1b/b7/aa63e25c8f14f4f2ae7b04e6097bdecb770e455c5c1ee0a600
#34 26.13 Successfully built location-service
#34 26.20 Installing collected packages: ulid-py, websockets, uvloop, typing-extensions, pyyaml, python-ulid, python-multipart, python-dotenv, prometheus-client, Pillow, MarkupSafe, idna, httptools, h11, greenlet, et-xmlfile, click, certifi, canonicaljson, asyncpg, annotated-types, annotated-doc, uvicorn, typing-inspection, sqlalchemy, pydantic-core, openpyxl, Mako, httpcore, anyio, watchfiles, starlette, pydantic, httpx, alembic, pydantic-settings, fastapi, location-service
#34 31.48 
#34 31.49 Successfully installed Mako-1.3.10 MarkupSafe-3.0.3 Pillow-12.1.1 alembic-1.18.4 annotated-doc-0.0.4 annotated-types-0.7.0 anyio-4.13.0 asyncpg-0.31.0 canonicaljson-2.0.0 certifi-2026.2.25 click-8.3.1 et-xmlfile-2.0.0 fastapi-0.135.2 greenlet-3.3.2 h11-0.16.0 httpcore-1.0.9 httptools-0.7.1 httpx-0.28.1 idna-3.11 location-service-0.1.0 openpyxl-3.1.5 prometheus-client-0.24.1 pydantic-2.12.5 pydantic-core-2.41.5 pydantic-settings-2.13.1 python-dotenv-1.2.2 python-multipart-0.0.22 python-ulid-3.1.0 pyyaml-6.0.3 sqlalchemy-2.0.48 starlette-1.0.0 typing-extensions-4.15.0 typing-inspection-0.4.2 ulid-py-1.1.0 uvicorn-0.42.0 uvloop-0.22.1 watchfiles-1.1.1 websockets-16.0
#34 31.49 WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager, possibly rendering your system unusable. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv. Use the --root-user-action option if you know what you are doing and want to suppress this warning.
#34 DONE 32.9s

#39 [location-service] exporting to image
#39 exporting layers
#39 exporting layers 5.2s done
#39 exporting manifest sha256:cc1ab6650b60d3a2822e66313b124a562f8e97f4ba65741b162c5ac01b36f525 0.0s done
#39 exporting config sha256:325dab3c2ebc1c3820481b0075630c47c3c63fa9c3744163a92dba7cdc1c2165 0.0s done
#39 exporting attestation manifest sha256:85924b4a8c012a031c486f572b81a002d1c848f6c11f5a82029b915e6142ba0b 0.0s done
#39 exporting manifest list sha256:b64ac8ff2d9d3a424ac73cccc39fafe86fac5bbd133c62f558ced31220f9da5e 0.0s done
#39 naming to docker.io/library/task-0012-location-service:latest done
#39 unpacking to docker.io/library/task-0012-location-service:latest
#39 unpacking to docker.io/library/task-0012-location-service:latest 3.2s done
#39 DONE 8.6s

#40 [location-service] resolving provenance for metadata file
#40 DONE 0.0s
 Image task-0012-fleet-stub Built 
 Image task-0012-location-service Built 
 Image task-0012-trip-service Built 
 Image task-0012-excel-stub Built 
 Image task-0012-telegram-stub Built 
 Network task-0012_default Creating 
 Network task-0012_default Created 
 Container task-0012-redpanda-1 Creating 
 Container task-0012-fleet-stub-1 Creating 
 Container task-0012-postgres-1 Creating 
 Container task-0012-telegram-stub-1 Creating 
 Container task-0012-excel-stub-1 Creating 
 Container task-0012-excel-stub-1 Created 
 Container task-0012-telegram-stub-1 Created 
 Container task-0012-redpanda-1 Created 
 Container task-0012-postgres-1 Created 
 Container task-0012-location-service-1 Creating 
 Container task-0012-fleet-stub-1 Created 
 Container task-0012-location-service-1 Created 
 Container task-0012-trip-service-1 Creating 
 Container task-0012-trip-service-1 Created 
 Container task-0012-fleet-stub-1 Starting 
 Container task-0012-postgres-1 Starting 
 Container task-0012-excel-stub-1 Starting 
 Container task-0012-redpanda-1 Starting 
 Container task-0012-telegram-stub-1 Starting 
 Container task-0012-telegram-stub-1 Started 
 Container task-0012-excel-stub-1 Started 
 Container task-0012-fleet-stub-1 Started 
 Container task-0012-redpanda-1 Started 
 Container task-0012-postgres-1 Started 
 Container task-0012-postgres-1 Waiting 
 Container task-0012-postgres-1 Healthy 
 Container task-0012-location-service-1 Starting 
 Container task-0012-location-service-1 Started 
 Container task-0012-postgres-1 Waiting 
 Container task-0012-postgres-1 Healthy 
 Container task-0012-trip-service-1 Starting 
 Container task-0012-trip-service-1 Started 
Waiting for trip-service /health...
curl: (52) Empty reply from server
Running alembic migrations inside service containers...
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> a1b2c3d4e5f6, trip_service_baseline
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 9f4e4fe14d8c, initial_schema
Seeding location-service database...
You are now connected to database "location_service" as user "postgres".
INSERT 0 2
INSERT 0 1
INSERT 0 2
UPDATE 1
INSERT 0 2
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

`

Notes:
- The smoke script completed functional steps but returned a non-zero exit due to a PowerShell NativeCommandError emitted during docker build output ("Image ... Building").
- One curl: (52) Empty reply from server appeared during health probing.

---

## Manual Checks

| What | How | Result |
|------|-----|--------|
| File inventory | Enumerated scoped files for trip-service, location-service, and TASK-0012 operational scripts | 92 files / 13,568 lines reviewed |

---

## Tests That Could Not Run

| Test | Reason | What Enables It |
|------|--------|-----------------|
| None | - | - |
