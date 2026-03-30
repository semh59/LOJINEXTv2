"""Shared HTTPX clients for downstream dependency and worker calls."""

from __future__ import annotations

import asyncio

import httpx

from trip_service.config import settings

_dependency_client: httpx.AsyncClient | None = None
_worker_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


def _build_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=settings.dependency_timeout_seconds)


async def get_dependency_client() -> httpx.AsyncClient:
    """Return the long-lived client used by request-time dependency calls."""
    global _dependency_client
    async with _client_lock:
        if _dependency_client is None or _dependency_client.is_closed:
            _dependency_client = _build_client()
        return _dependency_client


async def get_worker_client() -> httpx.AsyncClient:
    """Return the long-lived client used by background workers."""
    global _worker_client
    async with _client_lock:
        if _worker_client is None or _worker_client.is_closed:
            _worker_client = _build_client()
        return _worker_client


async def close_http_clients() -> None:
    """Close any shared clients so process shutdown does not leak sockets."""
    global _dependency_client, _worker_client

    async with _client_lock:
        clients = [client for client in (_dependency_client, _worker_client) if client is not None]
        _dependency_client = None
        _worker_client = None

    for client in clients:
        if not client.is_closed:
            await client.aclose()
