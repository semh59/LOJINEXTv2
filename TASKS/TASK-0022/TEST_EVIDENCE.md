# TEST_EVIDENCE.md

## Ruff (location-service)
Command:
`ruff check src tests`

Output:
```
All checks passed!
```

---
## Pytest (initial attempt, failed)
Command:
`pytest`

Output:
```
ImportError while loading conftest 'D:\PROJECT\LOJINEXTv2\services\location-service\tests\conftest.py'.
tests\conftest.py:16: in <module>
    from location_service.config import settings
E   ModuleNotFoundError: No module named 'location_service'
```

---
## Pytest (with PYTHONPATH)
Command:
`$env:PYTHONPATH="src"; pytest`

Output:
```
============================= test session starts =============================
platform win32 -- Python 3.14.2, pytest-9.0.1, pluggy-1.6.0
rootdir: D:\PROJECT\LOJINEXTv2\services\location-service
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.12.0, asyncio-1.3.0, cov-7.0.0, respx-0.22.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=session, asyncio_default_test_loop_scope=function
collected 99 items

tests\test_audit_findings.py .............                               [ 13%]
tests\test_auth.py .........                                             [ 22%]
tests\test_config.py .....                                               [ 27%]
tests\test_contract.py ......                                            [ 33%]
tests\test_internal_routes.py .......                                    [ 40%]
tests\test_mock_pipeline.py .                                            [ 41%]
tests\test_pairs_api.py .............                                    [ 54%]
tests\test_points_api.py .......                                         [ 61%]
tests\test_processing_flow.py ..........                                 [ 71%]
tests\test_providers.py ......                                           [ 77%]
tests\test_route_versions_api.py ...                                     [ 80%]
tests\test_schema.py .                                                   [ 81%]
tests\test_schema_integration.py .....                                   [ 86%]
tests\test_unit.py .............                                         [100%]

============================= 99 passed in 42.44s =============================
```

---
## Alembic Upgrade (local)
Command:
`$env:LOCATION_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/location_service"; alembic upgrade head`

Output:
```
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Scripts\alembic.exe\__main__.py", line 6, in <module>
    sys.exit(main())
             ~~~~^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\alembic\config.py", line 1033, in main
    CommandLine(prog=prog).main(argv=argv)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\alembic\config.py", line 1023, in main
    self.run_cmd(cfg, options)
    ~~~~~~~~~~~~^^^^^^^^^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\alembic\config.py", line 957, in run_cmd
    fn(
    ~~^
        config,
        ^^^^^^^
        *[getattr(options, k, None) for k in positional],
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        **{k: getattr(options, k, None) for k in kwarg},
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\alembic\command.py", line 483, in upgrade
    script.run_env()
    ~~~~~~~~~~~~~~^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\alembic\script\base.py", line 545, in run_env
    util.load_python_file(self.dir, "env.py")
    ~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\alembic\util\pyfiles.py", line 116, in load_python_file
    module = load_module_py(module_id, path)
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\alembic\util\pyfiles.py", line 136, in load_module_py
    spec.loader.exec_module(module)  # type: ignore
    ~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^
  File "<frozen importlib._bootstrap_external>", line 759, in exec_module
  File "<frozen importlib._bootstrap>", line 491, in _call_with_frames_removed
  File "D:\PROJECT\LOJINEXTv2\services\location-service\alembic\env.py", line 65, in <module>
    run_migrations_online()
    ~~~~~~~~~~~~~~~~~~~~~^^
  File "D:\PROJECT\LOJINEXTv2\services\location-service\alembic\env.py", line 59, in run_migrations_online
    asyncio.run(run_async_migrations())
    ~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\asyncio\runners.py", line 204, in run
    return runner.run(main)
           ~~~~~~~~~~^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\asyncio\runners.py", line 127, in run
    return self._loop.run_until_complete(task)
           ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\asyncio\base_events.py", line 719, in run_until_complete
    return future.result()
           ~~~~~~~~~~~~~^^
  File "D:\PROJECT\LOJINEXTv2\services\location-service\alembic\env.py", line 52, in run_async_migrations
    async with connectable.connect() as connection:
               ~~~~~~~~~~~~~~~~~~~^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\ext\asyncio\base.py", line 121, in __aenter__
    return await self.start(is_ctxmanager=True)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\ext\asyncio\engine.py", line 275, in start
    await greenlet_spawn(self.sync_engine.connect)
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\util\_concurrency_py3k.py", line 201, in greenlet_spawn
    result = context.throw(*sys.exc_info())
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\engine\base.py", line 3277, in connect
    return self._connection_cls(self)
           ~~~~~~~~~~~~~~~~~~~~^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\engine\base.py", line 143, in __init__
    self._dbapi_connection = engine.raw_connection()
                             ~~~~~~~~~~~~~~~~~~~~~^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\engine\base.py", line 3301, in raw_connection
    return self.pool.connect()
           ~~~~~~~~~~~~~~~~~^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\pool\base.py", line 447, in connect
    return _ConnectionFairy._checkout(self)
           ~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\pool\base.py", line 1264, in _checkout
    fairy = _ConnectionRecord.checkout(pool)
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\pool\base.py", line 711, in checkout
    rec = pool._do_get()
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\pool\impl.py", line 306, in _do_get
    return self._create_connection()
           ~~~~~~~~~~~~~~~~~~~~~~~^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\pool\base.py", line 388, in _create_connection
    return _ConnectionRecord(self)
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\pool\base.py", line 673, in __init__
    self.__connect()
    ~~~~~~~~~~~~~~^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\pool\base.py", line 899, in __connect
    with util.safe_reraise():
         ~~~~~~~~~~~~~~~~~^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\util\langhelpers.py", line 224, in __exit__
    raise exc_value.with_traceback(exc_tb)
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\pool\base.py", line 895, in __connect
    self.dbapi_connection = connection = pool._invoke_creator(self)
                                         ~~~~~~~~~~~~~~~~~~~~^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\engine\create.py", line 661, in connect
    return dialect.connect(*cargs, **cparams)
           ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\engine\default.py", line 629, in connect
    return self.loaded_dbapi.connect(*cargs, **cparams)  # type: ignore[no-any-return]  # NOQA: E501
           ~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\dialects\postgresql\asyncpg.py", line 955, in connect
    await_only(creator_fn(*arg, **kw)),
    ~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\util\_concurrency_py3k.py", line 132, in await_only
    return current.parent.switch(awaitable)  # type: ignore[no-any-return,attr-defined] # noqa: E501
           ~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\sqlalchemy\util\_concurrency_py3k.py", line 196, in greenlet_spawn
    value = await result
            ^^^^^^^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\asyncpg\connection.py", line 2443, in connect
    return await connect_utils._connect(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<22 lines>...
    )
    ^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\asyncpg\connect_utils.py", line 1218, in _connect
    conn = await _connect_addr(
           ^^^^^^^^^^^^^^^^^^^^
    ...<6 lines>...
    )
    ^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\asyncpg\connect_utils.py", line 1054, in _connect_addr
    return await __connect_addr(params, True, *args)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\site-packages\asyncpg\connect_utils.py", line 1102, in __connect_addr
    await connected
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "postgres"
```

---
## Docker Smoke (live providers)
Command:
`powershell -ExecutionPolicy Bypass -File TASKS/TASK-0012/scripts/smoke.ps1 -UseLiveProviders`

Output:
```
Starting docker smoke stack...
#1 [internal] load local bake definitions
#1 reading from stdin 2.63kB 0.1s done
#1 DONE 0.1s

#2 [trip-service internal] load build definition from Dockerfile
#2 DONE 0.0s

#2 [trip-service internal] load build definition from Dockerfile
#2 transferring dockerfile: 603B 0.0s done
#2 DONE 0.1s

#3 [excel-stub internal] load build definition from Dockerfile
#3 transferring dockerfile: 360B 0.0s done
#3 DONE 0.1s

#4 [location-service internal] load build definition from Dockerfile
#4 transferring dockerfile: 608B 0.0s done
#4 DONE 0.1s

#5 [fleet-stub internal] load metadata for docker.io/library/python:3.12-slim
#5 ...

#6 [auth] library/python:pull token for registry-1.docker.io
#6 DONE 0.0s

#5 [telegram-stub internal] load metadata for docker.io/library/python:3.12-slim
#5 DONE 1.1s

#7 [fleet-stub internal] load .dockerignore
#7 transferring context: 2B 0.0s done
#7 DONE 0.0s

#8 [location-service internal] load .dockerignore
#8 transferring context: 2B done
#8 DONE 0.0s

#9 [trip-service internal] load .dockerignore
#9 transferring context: 123B 0.0s done
#9 DONE 0.0s

#10 [trip-service internal] load build context
#10 DONE 0.0s

#11 [location-service internal] load build context
#11 DONE 0.0s

#12 [telegram-stub internal] load build context
#12 transferring context: 63B done
#12 DONE 0.0s

#13 [location-service 1/5] FROM docker.io/library/python:3.12-slim@sha256:3d5ed973e45820f5ba5e46bd065bd88b3a504ff0724d85980dcd05eab361fcf4
#13 resolve docker.io/library/python:3.12-slim@sha256:3d5ed973e45820f5ba5e46bd065bd88b3a504ff0724d85980dcd05eab361fcf4 0.0s done
#13 resolve docker.io/library/python:3.12-slim@sha256:3d5ed973e45820f5ba5e46bd065bd88b3a504ff0724d85980dcd05eab361fcf4 0.0s done
#13 DONE 0.1s

#14 [telegram-stub 2/5] WORKDIR /app
#14 CACHED

#15 [telegram-stub 3/5] COPY requirements.txt ./
#15 CACHED

#16 [telegram-stub 4/5] RUN python -m pip install --upgrade pip     && python -m pip install --no-cache-dir -r requirements.txt
#16 CACHED

#17 [excel-stub 5/5] COPY app.py ./
#17 CACHED

#10 [trip-service internal] load build context
#10 transferring context: 4.85kB 0.1s done
#10 DONE 0.1s

#11 [location-service internal] load build context
#11 transferring context: 158.51kB 0.1s done
#11 DONE 0.2s

#18 [telegram-stub] exporting to image
#18 exporting layers 0.0s done
#18 exporting manifest sha256:a970529cca435ee9e1df845488de70ef2ea84a2a82588cfac7d97472f0c11de9 done
#18 exporting config sha256:d7ce34f903645f8e968fd46f46d807fab1d49910ef255fe346edde52d45d349e done
#18 ...

#19 [trip-service 5/9] COPY pyproject.toml ./
#19 CACHED

#20 [trip-service 6/9] COPY alembic.ini ./
#20 CACHED

#21 [trip-service 7/9] COPY alembic ./alembic
#21 CACHED

#22 [trip-service 8/9] COPY src ./src
#22 CACHED

#23 [trip-service 9/9] RUN python -m pip install --upgrade pip     && python -m pip install --no-cache-dir .
#23 CACHED

#24 [location-service 2/9] RUN apt-get update     && apt-get install -y --no-install-recommends tzdata ca-certificates     && rm -rf /var/lib/apt/lists/*
#24 CACHED

#25 [location-service 6/9] COPY alembic.ini ./
#25 CACHED

#26 [location-service 5/9] COPY pyproject.toml ./
#26 CACHED

#27 [location-service 4/9] RUN useradd --create-home --shell /usr/sbin/nologin appuser
#27 CACHED

#28 [location-service 3/9] WORKDIR /app
#28 CACHED

#29 [location-service 7/9] COPY alembic ./alembic
#29 CACHED

#18 [telegram-stub] exporting to image
#18 exporting attestation manifest sha256:2b7bd72e887672b85c170ed2daf2b6bb274b1d9a76f63411a1e625179d406a5a
#18 ...

#30 [location-service 8/9] COPY src ./src
#30 DONE 0.2s

#18 [telegram-stub] exporting to image
#18 exporting attestation manifest sha256:2b7bd72e887672b85c170ed2daf2b6bb274b1d9a76f63411a1e625179d406a5a 0.2s done
#18 exporting manifest list sha256:c9c228968c2a312c25a1dff3dd726b1d6b136821df49158f2887d8ae6111aec8
#18 exporting manifest list sha256:c9c228968c2a312c25a1dff3dd726b1d6b136821df49158f2887d8ae6111aec8 0.1s done
#18 naming to docker.io/library/task-0012-telegram-stub:latest 0.0s done
#18 unpacking to docker.io/library/task-0012-telegram-stub:latest
#18 unpacking to docker.io/library/task-0012-telegram-stub:latest 0.0s done
#18 DONE 0.6s

#31 [trip-service] exporting to image
#31 exporting layers 0.0s done
#31 exporting manifest sha256:a372e5ee1c7251c93f655897e90f9af3a6e2d611b0dcfd58738650313b9a3475 0.0s done
#31 exporting config sha256:5b49a4c67b18a3eb4baa0e6d6ba011b0b9d49407013d00a1839935db111a2b6d 0.0s done
#31 exporting attestation manifest sha256:e756ff966f93ec0ab02739587db27d732f92017e3ec0232510bc8bfe602c1f74 0.1s done
#31 exporting manifest list sha256:8653bc66219ca7b083b6c18734c201f6dc139657735a9e0bd6fc59e29e2cdaf2 0.1s done
#31 naming to docker.io/library/task-0012-trip-service:latest done
#31 unpacking to docker.io/library/task-0012-trip-service:latest
#31 unpacking to docker.io/library/task-0012-trip-service:latest 0.1s done
#31 DONE 0.7s

#32 [fleet-stub] exporting to image
#32 exporting layers 0.0s done
#32 exporting manifest sha256:d4548a5b95762d17a4a9d5a3cd3f8fd17b89948fe13ba969ef8ba92f6523d39b done
#32 exporting config sha256:3f70b4e45be87f67f1184aae29957b2530bf7b9fae8fc7a215ae341e5b0ddd7c done
#32 exporting attestation manifest sha256:8f0b38fe8ee4526125671cf9c38457f74f799d8605653134d2e0e4def8fa2b87 0.2s done
#32 exporting manifest list sha256:dc67139fb692c000e1e4fb846a99adde4ed8ff2ab8436906a5e05a72458f92e1 0.1s done
#32 naming to docker.io/library/task-0012-fleet-stub:latest 0.0s done
#32 unpacking to docker.io/library/task-0012-fleet-stub:latest 0.0s done
#32 DONE 0.6s

#33 [excel-stub] exporting to image
#33 exporting layers 0.1s done
#33 exporting manifest sha256:95e010888548fd4f7a4bb7c6ce40af79aa07f877f885e020001b2c6787041926 0.0s done
#33 exporting config sha256:8411f55a43d22a5865835a1bcb262bb0f103e8b9568d649e9a9f600742c958bb 0.0s done
#33 exporting attestation manifest sha256:33c835333a361bd138faa3acc948afd288b080aa63a52b045e352133eeca2781 0.2s done
#33 exporting manifest list sha256:e0ce687ed57c2ee8b721420d624957b020c86d9c32305fcf9b233c53093fdf73 0.1s done
#33 naming to docker.io/library/task-0012-excel-stub:latest 0.0s done
#33 unpacking to docker.io/library/task-0012-excel-stub:latest 0.0s done
#33 DONE 0.7s

#34 [location-service 9/9] RUN python -m pip install --upgrade pip     && python -m pip install --no-cache-dir .
#34 ...

#35 [telegram-stub] resolving provenance for metadata file
#35 DONE 0.0s

#36 [excel-stub] resolving provenance for metadata file
#36 DONE 0.0s

#37 [trip-service] resolving provenance for metadata file
#37 DONE 0.0s

#38 [fleet-stub] resolving provenance for metadata file
#38 DONE 0.0s

#34 [location-service 9/9] RUN python -m pip install --upgrade pip     && python -m pip install --no-cache-dir .
#34 2.838 Requirement already satisfied: pip in /usr/local/lib/python3.12/site-packages (25.0.1)
#34 3.107 Collecting pip
#34 3.347   Downloading pip-26.0.1-py3-none-any.whl.metadata (4.7 kB)
#34 3.421 Downloading pip-26.0.1-py3-none-any.whl (1.8 MB)
#34 3.807    ???????????????????????????????????????? 1.8/1.8 MB 7.6 MB/s eta 0:00:00
#34 3.827 Installing collected packages: pip
#34 3.828   Attempting uninstall: pip
#34 3.831     Found existing installation: pip 25.0.1
#34 3.890     Uninstalling pip-25.0.1:
#34 4.259       Successfully uninstalled pip-25.0.1
#34 5.569 Successfully installed pip-26.0.1
#34 5.570 WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager, possibly rendering your system unusable. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv. Use the --root-user-action option if you know what you are doing and want to suppress this warning.
#34 7.229 Processing ./.
#34 7.234   Installing build dependencies: started
#34 9.596   Installing build dependencies: finished with status 'done'
#34 9.598   Getting requirements to build wheel: started
#34 10.67   Getting requirements to build wheel: finished with status 'done'
#34 10.67   Preparing metadata (pyproject.toml): started
#34 11.67   Preparing metadata (pyproject.toml): finished with status 'done'
#34 12.09 Collecting fastapi>=0.115.0 (from location-service==0.1.0)
#34 12.30   Downloading fastapi-0.135.2-py3-none-any.whl.metadata (28 kB)
#34 12.40 Collecting uvicorn>=0.30.0 (from uvicorn[standard]>=0.30.0->location-service==0.1.0)
#34 12.46   Downloading uvicorn-0.42.0-py3-none-any.whl.metadata (6.7 kB)
#34 13.03 Collecting sqlalchemy>=2.0.30 (from sqlalchemy[asyncio]>=2.0.30->location-service==0.1.0)
#34 13.09   Downloading sqlalchemy-2.0.48-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (9.5 kB)
#34 13.20 Collecting asyncpg>=0.30.0 (from location-service==0.1.0)
#34 13.27   Downloading asyncpg-0.31.0-cp312-cp312-manylinux_2_28_x86_64.whl.metadata (4.4 kB)
#34 13.34 Collecting alembic>=1.13.0 (from location-service==0.1.0)
#34 13.40   Downloading alembic-1.18.4-py3-none-any.whl.metadata (7.2 kB)
#34 13.61 Collecting pydantic>=2.7.0 (from location-service==0.1.0)
#34 13.67   Downloading pydantic-2.12.5-py3-none-any.whl.metadata (90 kB)
#34 13.81 Collecting pydantic-settings>=2.3.0 (from location-service==0.1.0)
#34 13.87   Downloading pydantic_settings-2.13.1-py3-none-any.whl.metadata (3.4 kB)
#34 14.04 Collecting python-ulid>=3.0.0 (from location-service==0.1.0)
#34 14.10   Downloading python_ulid-3.1.0-py3-none-any.whl.metadata (5.8 kB)
#34 14.18 Collecting httpx>=0.27.0 (from location-service==0.1.0)
#34 14.24   Downloading httpx-0.28.1-py3-none-any.whl.metadata (7.1 kB)
#34 14.31 Collecting prometheus-client>=0.20.0 (from location-service==0.1.0)
#34 14.37   Downloading prometheus_client-0.24.1-py3-none-any.whl.metadata (2.1 kB)
#34 14.76 Collecting Pillow>=10.0.0 (from location-service==0.1.0)
#34 14.82   Downloading pillow-12.1.1-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl.metadata (8.8 kB)
#34 14.99 Collecting canonicaljson>=2.0.0 (from location-service==0.1.0)
#34 15.05   Downloading canonicaljson-2.0.0-py3-none-any.whl.metadata (2.6 kB)
#34 15.12 Collecting PyJWT>=2.10.1 (from location-service==0.1.0)
#34 15.18   Downloading pyjwt-2.12.1-py3-none-any.whl.metadata (4.1 kB)
#34 15.25 Collecting Mako (from alembic>=1.13.0->location-service==0.1.0)
#34 15.32   Downloading mako-1.3.10-py3-none-any.whl.metadata (2.9 kB)
#34 15.38 Collecting typing-extensions>=4.12 (from alembic>=1.13.0->location-service==0.1.0)
#34 15.44   Downloading typing_extensions-4.15.0-py3-none-any.whl.metadata (3.3 kB)
#34 15.52 Collecting starlette>=0.46.0 (from fastapi>=0.115.0->location-service==0.1.0)
#34 15.58   Downloading starlette-1.0.0-py3-none-any.whl.metadata (6.3 kB)
#34 15.96 Collecting typing-inspection>=0.4.2 (from fastapi>=0.115.0->location-service==0.1.0)
#34 16.02   Downloading typing_inspection-0.4.2-py3-none-any.whl.metadata (2.6 kB)
#34 16.09 Collecting annotated-doc>=0.0.2 (from fastapi>=0.115.0->location-service==0.1.0)
#34 16.15   Downloading annotated_doc-0.0.4-py3-none-any.whl.metadata (6.6 kB)
#34 16.26 Collecting anyio (from httpx>=0.27.0->location-service==0.1.0)
#34 16.33   Downloading anyio-4.13.0-py3-none-any.whl.metadata (4.5 kB)
#34 16.41 Collecting certifi (from httpx>=0.27.0->location-service==0.1.0)
#34 16.47   Downloading certifi-2026.2.25-py3-none-any.whl.metadata (2.5 kB)
#34 16.55 Collecting httpcore==1.* (from httpx>=0.27.0->location-service==0.1.0)
#34 16.62   Downloading httpcore-1.0.9-py3-none-any.whl.metadata (21 kB)
#34 16.68 Collecting idna (from httpx>=0.27.0->location-service==0.1.0)
#34 16.74   Downloading idna-3.11-py3-none-any.whl.metadata (8.4 kB)
#34 16.81 Collecting h11>=0.16 (from httpcore==1.*->httpx>=0.27.0->location-service==0.1.0)
#34 16.87   Downloading h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
#34 16.94 Collecting annotated-types>=0.6.0 (from pydantic>=2.7.0->location-service==0.1.0)
#34 16.99   Downloading annotated_types-0.7.0-py3-none-any.whl.metadata (15 kB)
#34 18.44 Collecting pydantic-core==2.41.5 (from pydantic>=2.7.0->location-service==0.1.0)
#34 18.50   Downloading pydantic_core-2.41.5-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (7.3 kB)
#34 18.57 Collecting python-dotenv>=0.21.0 (from pydantic-settings>=2.3.0->location-service==0.1.0)
#34 18.64   Downloading python_dotenv-1.2.2-py3-none-any.whl.metadata (27 kB)
#34 18.96 Collecting greenlet>=1 (from sqlalchemy>=2.0.30->sqlalchemy[asyncio]>=2.0.30->location-service==0.1.0)
#34 19.02   Downloading greenlet-3.3.2-cp312-cp312-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl.metadata (3.7 kB)
#34 19.10 Collecting click>=7.0 (from uvicorn>=0.30.0->uvicorn[standard]>=0.30.0->location-service==0.1.0)
#34 19.16   Downloading click-8.3.1-py3-none-any.whl.metadata (2.6 kB)
#34 19.25 Collecting httptools>=0.6.3 (from uvicorn[standard]>=0.30.0->location-service==0.1.0)
#34 19.31   Downloading httptools-0.7.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (3.5 kB)
#34 19.41 Collecting pyyaml>=5.1 (from uvicorn[standard]>=0.30.0->location-service==0.1.0)
#34 19.47   Downloading pyyaml-6.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (2.4 kB)
#34 19.58 Collecting uvloop>=0.15.1 (from uvicorn[standard]>=0.30.0->location-service==0.1.0)
#34 19.65   Downloading uvloop-0.22.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (4.9 kB)
#34 19.81 Collecting watchfiles>=0.20 (from uvicorn[standard]>=0.30.0->location-service==0.1.0)
#34 19.86   Downloading watchfiles-1.1.1-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (4.9 kB)
#34 20.04 Collecting websockets>=10.4 (from uvicorn[standard]>=0.30.0->location-service==0.1.0)
#34 20.10   Downloading websockets-16.0-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (6.8 kB)
#34 20.23 Collecting MarkupSafe>=0.9.2 (from Mako->alembic>=1.13.0->location-service==0.1.0)
#34 20.29   Downloading markupsafe-3.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (2.7 kB)
#34 20.35 Downloading alembic-1.18.4-py3-none-any.whl (263 kB)
#34 20.51 Downloading asyncpg-0.31.0-cp312-cp312-manylinux_2_28_x86_64.whl (3.5 MB)
#34 21.50    ???????????????????????????????????????? 3.5/3.5 MB 3.6 MB/s  0:00:00
#34 21.55 Downloading canonicaljson-2.0.0-py3-none-any.whl (7.9 kB)
#34 21.62 Downloading fastapi-0.135.2-py3-none-any.whl (117 kB)
#34 21.69 Downloading annotated_doc-0.0.4-py3-none-any.whl (5.3 kB)
#34 21.75 Downloading httpx-0.28.1-py3-none-any.whl (73 kB)
#34 21.82 Downloading httpcore-1.0.9-py3-none-any.whl (78 kB)
#34 21.89 Downloading h11-0.16.0-py3-none-any.whl (37 kB)
#34 21.95 Downloading pillow-12.1.1-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl (7.0 MB)
#34 23.66    ???????????????????????????????????????? 7.0/7.0 MB 4.1 MB/s  0:00:01
#34 23.73 Downloading prometheus_client-0.24.1-py3-none-any.whl (64 kB)
#34 23.79 Downloading pydantic-2.12.5-py3-none-any.whl (463 kB)
#34 23.96 Downloading pydantic_core-2.41.5-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.1 MB)
#34 24.42    ???????????????????????????????????????? 2.1/2.1 MB 4.6 MB/s  0:00:00
#34 24.49 Downloading annotated_types-0.7.0-py3-none-any.whl (13 kB)
#34 24.55 Downloading pydantic_settings-2.13.1-py3-none-any.whl (58 kB)
#34 24.62 Downloading pyjwt-2.12.1-py3-none-any.whl (29 kB)
#34 24.70 Downloading python_dotenv-1.2.2-py3-none-any.whl (22 kB)
#34 24.77 Downloading python_ulid-3.1.0-py3-none-any.whl (11 kB)
#34 24.83 Downloading sqlalchemy-2.0.48-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (3.3 MB)
#34 25.72    ???????????????????????????????????????? 3.3/3.3 MB 3.7 MB/s  0:00:00
#34 25.78 Downloading greenlet-3.3.2-cp312-cp312-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl (613 kB)
#34 25.92    ???????????????????????????????????????? 613.9/613.9 kB 4.4 MB/s  0:00:00
#34 25.98 Downloading starlette-1.0.0-py3-none-any.whl (72 kB)
#34 26.06 Downloading anyio-4.13.0-py3-none-any.whl (114 kB)
#34 26.14 Downloading idna-3.11-py3-none-any.whl (71 kB)
#34 26.20 Downloading typing_extensions-4.15.0-py3-none-any.whl (44 kB)
#34 26.27 Downloading typing_inspection-0.4.2-py3-none-any.whl (14 kB)
#34 26.33 Downloading uvicorn-0.42.0-py3-none-any.whl (68 kB)
#34 26.42 Downloading click-8.3.1-py3-none-any.whl (108 kB)
#34 26.52 Downloading httptools-0.7.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (517 kB)
#34 26.69 Downloading pyyaml-6.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (807 kB)
#34 26.86    ???????????????????????????????????????? 807.9/807.9 kB 4.8 MB/s  0:00:00
#34 26.93 Downloading uvloop-0.22.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (4.4 MB)
#34 27.98    ???????????????????????????????????????? 4.4/4.4 MB 4.2 MB/s  0:00:01
#34 28.04 Downloading watchfiles-1.1.1-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (456 kB)
#34 28.21 Downloading websockets-16.0-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (184 kB)
#34 28.31 Downloading certifi-2026.2.25-py3-none-any.whl (153 kB)
#34 28.41 Downloading mako-1.3.10-py3-none-any.whl (78 kB)
#34 28.47 Downloading markupsafe-3.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (22 kB)
#34 28.53 Building wheels for collected packages: location-service
#34 28.54   Building wheel for location-service (pyproject.toml): started
#34 29.70   Building wheel for location-service (pyproject.toml): finished with status 'done'
#34 29.70   Created wheel for location-service: filename=location_service-0.1.0-py3-none-any.whl size=51220 sha256=6dc4d0195894c2e6c4e2bebc81630cf3a7e38123987a6ce8a329e74d5ff534a5
#34 29.70   Stored in directory: /tmp/pip-ephem-wheel-cache-gizybrpb/wheels/54/1b/b7/aa63e25c8f14f4f2ae7b04e6097bdecb770e455c5c1ee0a600
#34 29.71 Successfully built location-service
#34 29.77 Installing collected packages: websockets, uvloop, typing-extensions, pyyaml, python-ulid, python-dotenv, PyJWT, prometheus-client, Pillow, MarkupSafe, idna, httptools, h11, greenlet, click, certifi, canonicaljson, asyncpg, annotated-types, annotated-doc, uvicorn, typing-inspection, sqlalchemy, pydantic-core, Mako, httpcore, anyio, watchfiles, starlette, pydantic, httpx, alembic, pydantic-settings, fastapi, location-service
#34 34.57 
#34 34.57 Successfully installed Mako-1.3.10 MarkupSafe-3.0.3 Pillow-12.1.1 PyJWT-2.12.1 alembic-1.18.4 annotated-doc-0.0.4 annotated-types-0.7.0 anyio-4.13.0 asyncpg-0.31.0 canonicaljson-2.0.0 certifi-2026.2.25 click-8.3.1 fastapi-0.135.2 greenlet-3.3.2 h11-0.16.0 httpcore-1.0.9 httptools-0.7.1 httpx-0.28.1 idna-3.11 location-service-0.1.0 prometheus-client-0.24.1 pydantic-2.12.5 pydantic-core-2.41.5 pydantic-settings-2.13.1 python-dotenv-1.2.2 python-ulid-3.1.0 pyyaml-6.0.3 sqlalchemy-2.0.48 starlette-1.0.0 typing-extensions-4.15.0 typing-inspection-0.4.2 uvicorn-0.42.0 uvloop-0.22.1 watchfiles-1.1.1 websockets-16.0
#34 34.57 WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager, possibly rendering your system unusable. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv. Use the --root-user-action option if you know what you are doing and want to suppress this warning.
#34 DONE 35.6s

#39 [location-service] exporting to image
#39 exporting layers
#39 exporting layers 5.8s done
#39 exporting manifest sha256:39ba8416bd7c76ef3fb278b8008386ef29a06421f455c448f9877dd578771d07 0.0s done
#39 exporting config sha256:f5273e9a41919cbce7dca22160fc96c6228b0f923633660fe58d95e27b006298 0.0s done
#39 exporting attestation manifest sha256:6ad92058d8147591285f7c73a8afb50d21d2fed33d343982d50a5bfc9ee393aa 0.0s done
#39 exporting manifest list sha256:fa1feb853f71ac73054d7e7e1b85ca48c5d88070583ca4fd0192cfe9680db500 0.0s done
#39 naming to docker.io/library/task-0012-location-service:latest
#39 naming to docker.io/library/task-0012-location-service:latest done
#39 unpacking to docker.io/library/task-0012-location-service:latest
#39 unpacking to docker.io/library/task-0012-location-service:latest 3.0s done
#39 DONE 8.9s

#40 [location-service] resolving provenance for metadata file
#40 DONE 0.0s
Waiting for trip-service /health...
Running alembic migrations inside service containers...
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> a1b2c3d4e5f6, trip_service_baseline
INFO  [alembic.runtime.migration] Running upgrade a1b2c3d4e5f6 -> b2c3d4e5f6a1, add outbox claims
docker : INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
At D:\PROJECT\LOJINEXTv2\TASKS\TASK-0012\scripts\smoke.ps1:39 char:29
+ ... = $Script | docker compose -f $compose exec -T $Service python - 2>&1 ...
+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (INFO  [alembic....PostgresqlImpl.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> a1b2c3d4e5f6, trip_service_baseline
INFO  [alembic.runtime.migration] Running upgrade a1b2c3d4e5f6 -> b2c3d4e5f6a1, add outbox claims
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 9f4e4fe14d8c, initial_schema
INFO  [alembic.runtime.migration] Running upgrade 9f4e4fe14d8c -> 0d5f12e97db6, remove_import_export
docker : INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
At D:\PROJECT\LOJINEXTv2\TASKS\TASK-0012\scripts\smoke.ps1:39 char:29
+ ... = $Script | docker compose -f $compose exec -T $Service python - 2>&1 ...
+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (INFO  [alembic....PostgresqlImpl.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 9f4e4fe14d8c, initial_schema
INFO  [alembic.runtime.migration] Running upgrade 9f4e4fe14d8c -> 0d5f12e97db6, remove_import_export
Seeding location-service database for offline smoke...
You are now connected to database "location_service" as user "postgres".
INSERT 0 2
INSERT 0 1
INSERT 0 2
UPDATE 1
INSERT 0 2
Generating JWT tokens in trip-service container...
Offline smoke: manual create trip...
Offline smoke: create empty return...
Offline smoke: Telegram full ingest...
Offline smoke: Telegram fallback ingest...
Offline smoke: Excel ingest...
Offline smoke: driver statement...
Offline smoke: hard delete flow...
Live smoke: creating points and pair in location-service...
Live smoke: validating location internal contracts...
Live smoke: validating trip/location integration...
Smoke completed.
 Container task-0012-trip-service-1 Stopping 
 Container task-0012-telegram-stub-1 Stopping 
 Container task-0012-excel-stub-1 Stopping 
 Container task-0012-telegram-stub-1 Stopped 
 Container task-0012-telegram-stub-1 Removing 
 Container task-0012-telegram-stub-1 Removed 
 Container task-0012-excel-stub-1 Stopped 
 Container task-0012-excel-stub-1 Removing 
 Container task-0012-excel-stub-1 Removed 
 Container task-0012-trip-service-1 Stopped 
 Container task-0012-trip-service-1 Removing 
 Container task-0012-trip-service-1 Removed 
 Container task-0012-fleet-stub-1 Stopping 
 Container task-0012-redpanda-1 Stopping 
 Container task-0012-location-service-1 Stopping 
 Container task-0012-redpanda-1 Stopped 
 Container task-0012-redpanda-1 Removing 
 Container task-0012-redpanda-1 Removed 
 Container task-0012-fleet-stub-1 Stopped 
 Container task-0012-fleet-stub-1 Removing 
 Container task-0012-fleet-stub-1 Removed 
 Container task-0012-location-service-1 Stopped 
 Container task-0012-location-service-1 Removing 
 Container task-0012-location-service-1 Removed 
 Container task-0012-postgres-1 Stopping 
 Container task-0012-postgres-1 Stopped 
 Container task-0012-postgres-1 Removing 
 Container task-0012-postgres-1 Removed 
 Network task-0012_default Removing 
 Network task-0012_default Removed 
 Image task-0012-telegram-stub Building 
 Image task-0012-excel-stub Building 
 Image task-0012-trip-service Building 
 Image task-0012-location-service Building 
 Image task-0012-fleet-stub Building 
 Image task-0012-telegram-stub Built 
 Image task-0012-location-service Built 
 Image task-0012-fleet-stub Built 
 Image task-0012-trip-service Built 
 Image task-0012-excel-stub Built 
 Network task-0012_default Creating 
 Network task-0012_default Created 
 Container task-0012-redpanda-1 Creating 
 Container task-0012-excel-stub-1 Creating 
 Container task-0012-fleet-stub-1 Creating 
 Container task-0012-postgres-1 Creating 
 Container task-0012-telegram-stub-1 Creating 
 Container task-0012-fleet-stub-1 Created 
 Container task-0012-redpanda-1 Created 
 Container task-0012-telegram-stub-1 Created 
 Container task-0012-postgres-1 Created 
 Container task-0012-location-service-1 Creating 
 Container task-0012-excel-stub-1 Created 
 Container task-0012-location-service-1 Created 
 Container task-0012-trip-service-1 Creating 
 Container task-0012-trip-service-1 Created 
 Container task-0012-telegram-stub-1 Starting 
 Container task-0012-redpanda-1 Starting 
 Container task-0012-excel-stub-1 Starting 
 Container task-0012-fleet-stub-1 Starting 
 Container task-0012-postgres-1 Starting 
 Container task-0012-fleet-stub-1 Started 
 Container task-0012-excel-stub-1 Started 
 Container task-0012-telegram-stub-1 Started 
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
```

---
## Load/Soak (location-service)
Command:
`python TASKS/TASK-0022/scripts/location_load.py` (with BASE_URL, ADMIN_TOKEN, SERVICE_TOKEN set)

Output:
```
Load test completed
Elapsed seconds: 17.50
Total requests: 56
Errors: 1
429 rate: 0.00%
Status counts:
  200: 31
  201: 18
  202: 6
  404: 1
Traceback (most recent call last):
  File "D:\PROJECT\LOJINEXTv2\TASKS\TASK-0022\scripts\location_load.py", line 260, in <module>
    asyncio.run(main())
    ~~~~~~~~~~~^^^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\asyncio\runners.py", line 204, in run
    return runner.run(main)
           ~~~~~~~~~~^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\asyncio\runners.py", line 127, in run
    return self._loop.run_until_complete(task)
           ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^
  File "C:\Users\semih\AppData\Local\Programs\Python\Python314\Lib\asyncio\base_events.py", line 719, in run_until_complete
    return future.result()
           ~~~~~~~~~~~~~^^
  File "D:\PROJECT\LOJINEXTv2\TASKS\TASK-0022\scripts\location_load.py", line 236, in main
    await asyncio.gather(*tasks)
  File "D:\PROJECT\LOJINEXTv2\TASKS\TASK-0022\scripts\location_load.py", line 232, in _start_worker
    await worker(idx, stop_at, metrics)
  File "D:\PROJECT\LOJINEXTv2\TASKS\TASK-0022\scripts\location_load.py", line 219, in worker
    await _scenario_mix(client, pair_id, origin_name, destination_name, metrics)
  File "D:\PROJECT\LOJINEXTv2\TASKS\TASK-0022\scripts\location_load.py", line 185, in _scenario_mix
    await _request(
    ...<11 lines>...
    )
  File "D:\PROJECT\LOJINEXTv2\TASKS\TASK-0022\scripts\location_load.py", line 70, in _request
    raise RuntimeError(f"{method} {url} failed with {resp.status_code}: {resp.text}")
RuntimeError: POST http://localhost:8103/internal/v1/routes/resolve failed with 404: {"type":"https://location-service/errors/LOCATION_ROUTE_RESOLUTION_NOT_FOUND","title":"Not found","status":404,"detail":"No active route matches the provided origin/destination/profile.","instance":"/internal/v1/routes/resolve","code":"LOCATION_ROUTE_RESOLUTION_NOT_FOUND","request_id":"93d0b6e9-9a1d-430f-91c6-8b02993d27a3"}
```
