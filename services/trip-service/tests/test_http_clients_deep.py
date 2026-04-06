"""Deep tests for shared HTTP client lifecycle."""

from __future__ import annotations

import pytest

import trip_service.http_clients as http_clients

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_dependency_client_is_reused_until_closed() -> None:
    await http_clients.close_http_clients()

    first = await http_clients.get_dependency_client()
    second = await http_clients.get_dependency_client()

    assert first is second
    assert not first.is_closed

    await first.aclose()
    recreated = await http_clients.get_dependency_client()

    assert recreated is not first
    assert not recreated.is_closed

    await http_clients.close_http_clients()


@pytest.mark.asyncio
async def test_worker_client_is_reused_and_separate_from_dependency_client() -> None:
    await http_clients.close_http_clients()

    dependency_client = await http_clients.get_dependency_client()
    worker_first = await http_clients.get_worker_client()
    worker_second = await http_clients.get_worker_client()

    assert worker_first is worker_second
    assert worker_first is not dependency_client

    await http_clients.close_http_clients()


@pytest.mark.asyncio
async def test_close_http_clients_resets_global_clients() -> None:
    await http_clients.close_http_clients()

    dependency_client = await http_clients.get_dependency_client()
    worker_client = await http_clients.get_worker_client()

    await http_clients.close_http_clients()

    assert dependency_client.is_closed is True
    assert worker_client.is_closed is True
    assert http_clients._dependency_client is None
    assert http_clients._worker_client is None
