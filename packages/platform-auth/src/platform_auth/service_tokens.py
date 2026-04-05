"""Shared service-token acquisition and caching helpers."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass

import httpx
import jwt


class ServiceTokenAcquisitionError(RuntimeError):
    """Raised when a service token cannot be acquired."""


@dataclass(frozen=True)
class CachedServiceToken:
    """Cached service token plus absolute expiry."""

    token: str
    expires_at_epoch: float


class ServiceTokenCache:
    """In-process cache for short-lived service-to-service tokens."""

    def __init__(
        self,
        *,
        refresh_skew_seconds: int = 60,
        failure_backoff_seconds: float = 5.0,
        request_timeout_seconds: float = 2.0,
    ) -> None:
        self._refresh_skew_seconds = refresh_skew_seconds
        self._failure_backoff_seconds = failure_backoff_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._entries: dict[tuple[str, str], CachedServiceToken] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._backoff_until: dict[tuple[str, str], float] = {}

    def readiness_state(
        self,
        *,
        service_name: str,
        audience: str | None,
        token_url: str,
        client_id: str,
        client_secret: str,
    ) -> str:
        """Return `cold`, `ok`, or `fail` for outbound auth readiness."""
        if not token_url.strip() or not client_id.strip() or not client_secret.strip():
            return "fail"
        entry = self._cached_entry((service_name, audience or ""))
        return "ok" if entry is not None else "cold"

    async def get_token(
        self,
        *,
        service_name: str,
        audience: str | None,
        token_url: str,
        client_id: str,
        client_secret: str,
    ) -> str:
        """Return a cached token or mint a fresh one from identity-service."""
        if not token_url.strip():
            raise ServiceTokenAcquisitionError("Service token URL is not configured.")
        if not client_id.strip():
            raise ServiceTokenAcquisitionError("Service client id is not configured.")
        if not client_secret.strip():
            raise ServiceTokenAcquisitionError("Service client secret is not configured.")

        key = (service_name, audience or "")
        cached = self._cached_entry(key)
        if cached is not None and not self._should_refresh(cached):
            return cached.token

        now = time.time()
        if self._backoff_until.get(key, 0.0) > now and cached is None:
            raise ServiceTokenAcquisitionError("Service token acquisition is temporarily backing off.")

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._cached_entry(key)
            if cached is not None and not self._should_refresh(cached):
                return cached.token

            try:
                refreshed = await self._fetch_token(
                    token_url=token_url,
                    client_id=client_id,
                    client_secret=client_secret,
                    audience=audience,
                )
            except ServiceTokenAcquisitionError:
                if cached is not None:
                    return cached.token
                self._backoff_until[key] = time.time() + self._failure_backoff_seconds
                raise

            self._entries[key] = refreshed
            self._backoff_until.pop(key, None)
            return refreshed.token

    def _cached_entry(self, key: tuple[str, str]) -> CachedServiceToken | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at_epoch <= time.time():
            self._entries.pop(key, None)
            return None
        return entry

    def _should_refresh(self, entry: CachedServiceToken) -> bool:
        return entry.expires_at_epoch - time.time() <= self._refresh_skew_seconds

    async def _fetch_token(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        audience: str | None,
    ) -> CachedServiceToken:
        delays = (0.0, random.uniform(0.2, 0.8), random.uniform(0.5, 1.5))
        last_error: Exception | None = None

        for attempt, delay in enumerate(delays, start=1):
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                return await self._request_token(
                    token_url=token_url,
                    client_id=client_id,
                    client_secret=client_secret,
                    audience=audience,
                )
            except ServiceTokenAcquisitionError as exc:
                last_error = exc
                if "401" in str(exc) or "403" in str(exc):
                    raise
                if attempt == len(delays):
                    break

        raise ServiceTokenAcquisitionError(str(last_error or "Service token acquisition failed."))

    async def _request_token(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        audience: str | None,
    ) -> CachedServiceToken:
        payload = {"client_id": client_id, "client_secret": client_secret}
        if audience:
            payload["audience"] = audience

        try:
            async with httpx.AsyncClient(timeout=self._request_timeout_seconds) as client:
                response = await client.post(token_url, json=payload)
        except httpx.HTTPError as exc:
            raise ServiceTokenAcquisitionError(f"Identity token request failed: {exc}") from exc

        if response.status_code in {401, 403}:
            raise ServiceTokenAcquisitionError(f"Identity token request returned {response.status_code}.")
        if response.status_code != 200:
            raise ServiceTokenAcquisitionError(f"Identity token request returned {response.status_code}.")

        try:
            data = response.json()
        except ValueError as exc:
            raise ServiceTokenAcquisitionError("Identity token response was not valid JSON.") from exc

        token = data.get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise ServiceTokenAcquisitionError("Identity token response did not include access_token.")

        expires_at_epoch = self._decode_expiry(token, fallback_ttl_seconds=int(data.get("expires_in", 300) or 300))
        return CachedServiceToken(token=token, expires_at_epoch=expires_at_epoch)

    @staticmethod
    def _decode_expiry(token: str, *, fallback_ttl_seconds: int) -> float:
        try:
            payload = jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": False, "verify_aud": False, "verify_iss": False},
                algorithms=["HS256", "RS256"],
            )
        except jwt.PyJWTError:
            return time.time() + max(fallback_ttl_seconds, 1)
        exp = payload.get("exp")
        if isinstance(exp, (int, float)):
            return float(exp)
        return time.time() + max(fallback_ttl_seconds, 1)
