import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt

from platform_auth.errors import KeyResolutionError
from platform_auth.settings import AuthSettings

logger = logging.getLogger("platform_auth.key_provider")

_JWKS_PROVIDER_CACHE: dict[tuple[str, int], "JWKSKeyProvider"] = {}


@dataclass
class StaticKeyProvider:
    """Key provider for local HMAC or RSA PEM material."""

    settings: AuthSettings

    def signing_key(self) -> str:
        """Return key material used for signing."""
        if self.settings.uses_hmac:
            if not self.settings.shared_secret:
                raise KeyResolutionError("shared_secret is required for HS* signing.")
            return self.settings.shared_secret
        if self.settings.uses_rsa:
            if not self.settings.private_key:
                raise KeyResolutionError("private_key is required for RS* signing.")
            return self.settings.private_key
        raise KeyResolutionError(f"Unsupported algorithm: {self.settings.algorithm}")

    async def async_verification_key(self, header: dict[str, Any]) -> Any:
        """Return key material used for verification (async wrapper)."""
        return self.verification_key(header)

    def verification_key(self, header: dict[str, Any]) -> Any:
        """Return key material used for verification."""
        del header
        if self.settings.uses_hmac:
            if not self.settings.shared_secret:
                raise KeyResolutionError("shared_secret is required for HS* verification.")
            return self.settings.shared_secret
        if self.settings.uses_rsa:
            if self.settings.public_key:
                return self.settings.public_key
            raise KeyResolutionError("public_key is required when no JWKS URL is configured.")
        raise KeyResolutionError(f"Unsupported algorithm: {self.settings.algorithm}")


@dataclass
class JWKSKeyProvider:
    """Verification provider backed by a remote JWKS document."""

    jwks_url: str
    cache_ttl_seconds: int = 300
    _cached_at: float = 0.0
    _keys: dict[str, Any] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def _get_client(self) -> httpx.Client:
        # Use a pooled client if possible, or create one
        return httpx.Client(timeout=5.0)

    async def _get_async_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=5.0)

    async def _load_jwks_async(self) -> dict[str, Any]:
        """Load JWKS document asynchronously."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(self.jwks_url)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise KeyResolutionError(
                f"Failed to fetch JWKS from {self.jwks_url} (async): {exc}"
            ) from exc

        return self._process_jwks_payload(payload)

    def _load_jwks_sync(self) -> dict[str, Any]:
        """Load JWKS document synchronously (legacy/fallback)."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(self.jwks_url)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise KeyResolutionError(
                f"Failed to fetch JWKS from {self.jwks_url} (sync): {exc}"
            ) from exc

        return self._process_jwks_payload(payload)

    def _process_jwks_payload(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
            raise KeyResolutionError("JWKS document did not contain a keys array.")

        keys: dict[str, Any] = {}
        for entry in payload["keys"]:
            if not isinstance(entry, dict):
                continue
            kid = str(entry.get("kid", "")).strip()
            if not kid:
                continue
            keys[kid] = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(entry))

        if not keys:
            raise KeyResolutionError("JWKS document did not contain usable RSA keys.")

        self._keys = keys
        self._cached_at = time.monotonic()
        return keys

    async def async_verification_key(self, header: dict[str, Any]) -> Any:
        """Return the RSA public key matching the token kid (async)."""
        kid = str(header.get("kid", "")).strip()
        if not kid:
            raise KeyResolutionError("RS256 token is missing kid header.")

        async with self._lock:
            if not self._keys or (time.monotonic() - self._cached_at >= self.cache_ttl_seconds):
                await self._load_jwks_async()

            key = self._keys.get(kid)
            if key is None:
                # Refresh if key not found (possible rotation)
                await self._load_jwks_async()
                key = self._keys.get(kid)

        if key is None:
            raise KeyResolutionError(f"JWKS key not found for kid={kid}.")
        return key

    def verification_key(self, header: dict[str, Any]) -> Any:
        """Return the RSA public key matching the token kid (sync fallback)."""
        kid = str(header.get("kid", "")).strip()
        if not kid:
            raise KeyResolutionError("RS256 token is missing kid header.")

        if not self._keys or (time.monotonic() - self._cached_at >= self.cache_ttl_seconds):
            self._load_jwks_sync()

        key = self._keys.get(kid)
        if key is None:
            self._load_jwks_sync()
            key = self._keys.get(kid)

        if key is None:
            raise KeyResolutionError(f"JWKS key not found for kid={kid}.")
        return key


def build_signing_provider(settings: AuthSettings) -> StaticKeyProvider:
    """Build the provider used to sign tokens."""
    return StaticKeyProvider(settings=settings)


def build_verification_provider(
    settings: AuthSettings,
) -> StaticKeyProvider | JWKSKeyProvider:
    """Build the provider used to verify tokens."""
    if settings.uses_rsa and settings.jwks_url:
        cache_key = (settings.jwks_url, settings.jwks_cache_ttl_seconds)
        provider = _JWKS_PROVIDER_CACHE.get(cache_key)
        if provider is None:
            provider = JWKSKeyProvider(
                jwks_url=settings.jwks_url,
                cache_ttl_seconds=settings.jwks_cache_ttl_seconds,
            )
            _JWKS_PROVIDER_CACHE[cache_key] = provider
        return provider
    return StaticKeyProvider(settings=settings)
