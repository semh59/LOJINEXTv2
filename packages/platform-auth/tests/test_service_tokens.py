from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from platform_auth.service_tokens import CachedServiceToken, ServiceTokenAcquisitionError, ServiceTokenCache


def test_service_token_cache_reuses_cached_token(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = ServiceTokenCache()
    calls = {"count": 0}

    async def fake_request_token(**_kwargs) -> CachedServiceToken:
        calls["count"] += 1
        return CachedServiceToken(token="token-1", expires_at_epoch=9999999999.0)

    monkeypatch.setattr(cache, "_request_token", fake_request_token)

    token_1 = asyncio.run(
        cache.get_token(
            service_name="trip-service",
            audience="aud",
            token_url="http://identity/auth/v1/token/service",
            client_id="trip-service",
            client_secret="secret",
        )
    )
    token_2 = asyncio.run(
        cache.get_token(
            service_name="trip-service",
            audience="aud",
            token_url="http://identity/auth/v1/token/service",
            client_id="trip-service",
            client_secret="secret",
        )
    )

    assert token_1 == token_2 == "token-1"
    assert calls["count"] == 1
    assert cache.readiness_state(
        service_name="trip-service",
        audience="aud",
        token_url="http://identity/auth/v1/token/service",
        client_id="trip-service",
        client_secret="secret",
    ) == "ok"


def test_service_token_cache_reports_cold_when_config_is_valid_but_empty() -> None:
    cache = ServiceTokenCache()

    assert cache.readiness_state(
        service_name="trip-service",
        audience="aud",
        token_url="http://identity/auth/v1/token/service",
        client_id="trip-service",
        client_secret="secret",
    ) == "cold"


def test_service_token_cache_uses_cached_token_on_refresh_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = ServiceTokenCache(refresh_skew_seconds=400)
    first_call = {"done": False}

    async def fake_request_token(**_kwargs) -> CachedServiceToken:
        if not first_call["done"]:
            first_call["done"] = True
            return CachedServiceToken(token="token-1", expires_at_epoch=time.time() + 120.0)
        raise ServiceTokenAcquisitionError("Identity token request returned 503.")

    monkeypatch.setattr(cache, "_request_token", fake_request_token)

    first = asyncio.run(
        cache.get_token(
            service_name="trip-service",
            audience="aud",
            token_url="http://identity/auth/v1/token/service",
            client_id="trip-service",
            client_secret="secret",
        )
    )
    second = asyncio.run(
        cache.get_token(
            service_name="trip-service",
            audience="aud",
            token_url="http://identity/auth/v1/token/service",
            client_id="trip-service",
            client_secret="secret",
        )
    )

    assert first == second == "token-1"


def test_service_token_cache_raises_when_identity_unavailable_and_cache_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = ServiceTokenCache()

    async def fail_request(**_kwargs) -> CachedServiceToken:
        raise ServiceTokenAcquisitionError("Identity token request failed.")

    monkeypatch.setattr(cache, "_request_token", fail_request)

    with pytest.raises(ServiceTokenAcquisitionError):
        asyncio.run(
            cache.get_token(
                service_name="trip-service",
                audience="aud",
                token_url="http://identity/auth/v1/token/service",
                client_id="trip-service",
                client_secret="secret",
            )
        )


def test_service_token_cache_refresh_threshold_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = ServiceTokenCache(refresh_skew_seconds=60)
    monkeypatch.setattr("platform_auth.service_tokens.time.time", lambda: 1_000.0)

    assert cache._should_refresh(CachedServiceToken(token="t61", expires_at_epoch=1_061.0)) is False
    assert cache._should_refresh(CachedServiceToken(token="t60", expires_at_epoch=1_060.0)) is True
    assert cache._should_refresh(CachedServiceToken(token="t59", expires_at_epoch=1_059.0)) is True
    assert cache._should_refresh(CachedServiceToken(token="t1", expires_at_epoch=1_001.0)) is True
    assert cache._cached_entry(("svc", "aud")) is None
    cache._entries[("svc", "aud")] = CachedServiceToken(token="expired", expires_at_epoch=1_000.0)
    assert cache._cached_entry(("svc", "aud")) is None


def test_service_token_cache_singleflight_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = ServiceTokenCache(refresh_skew_seconds=60)
    cache._entries[("trip-service", "lojinext-platform")] = CachedServiceToken(
        token="stale-token",
        expires_at_epoch=time.time() + 30.0,
    )
    calls = {"count": 0}

    async def fake_request_token(**_kwargs: Any) -> CachedServiceToken:
        calls["count"] += 1
        await asyncio.sleep(0.05)
        return CachedServiceToken(token="fresh-token", expires_at_epoch=time.time() + 300.0)

    monkeypatch.setattr(cache, "_request_token", fake_request_token)

    async def _run() -> tuple[str, str]:
        return await asyncio.gather(
            cache.get_token(
                service_name="trip-service",
                audience="lojinext-platform",
                token_url="http://identity/auth/v1/token/service",
                client_id="trip-service",
                client_secret="secret",
            ),
            cache.get_token(
                service_name="trip-service",
                audience="lojinext-platform",
                token_url="http://identity/auth/v1/token/service",
                client_id="trip-service",
                client_secret="secret",
            ),
        )

    first, second = asyncio.run(_run())

    assert first == "fresh-token"
    assert second == "fresh-token"
    assert calls["count"] == 1


def test_service_token_cache_short_backoff_after_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = ServiceTokenCache(failure_backoff_seconds=5.0)
    calls = {"count": 0}
    now = {"value": 1_000.0}

    async def fail_request(**_kwargs: Any) -> CachedServiceToken:
        calls["count"] += 1
        raise ServiceTokenAcquisitionError("Identity token request returned 503.")

    monkeypatch.setattr(cache, "_request_token", fail_request)
    monkeypatch.setattr("platform_auth.service_tokens.time.time", lambda: now["value"])

    with pytest.raises(ServiceTokenAcquisitionError):
        asyncio.run(
            cache.get_token(
                service_name="trip-service",
                audience="lojinext-platform",
                token_url="http://identity/auth/v1/token/service",
                client_id="trip-service",
                client_secret="secret",
            )
        )
    first_call_count = calls["count"]

    with pytest.raises(ServiceTokenAcquisitionError):
        asyncio.run(
            cache.get_token(
                service_name="trip-service",
                audience="lojinext-platform",
                token_url="http://identity/auth/v1/token/service",
                client_id="trip-service",
                client_secret="secret",
            )
        )

    assert first_call_count == 3
    assert calls["count"] == first_call_count
