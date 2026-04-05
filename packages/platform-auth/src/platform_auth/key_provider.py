"""Signing and verification key providers."""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any

import jwt

from platform_auth.errors import KeyResolutionError
from platform_auth.settings import AuthSettings

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

    def _load_jwks(self) -> dict[str, Any]:
        request = urllib.request.Request(self.jwks_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
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

    def verification_key(self, header: dict[str, Any]) -> Any:
        """Return the RSA public key matching the token kid."""
        kid = str(header.get("kid", "")).strip()
        if not kid:
            raise KeyResolutionError("RS256 token is missing kid header.")
        if not self._keys or time.monotonic() - self._cached_at >= self.cache_ttl_seconds:
            self._load_jwks()
        key = self._keys.get(kid)
        if key is None:
            key = self._load_jwks().get(kid)
        if key is None:
            raise KeyResolutionError(f"JWKS key not found for kid={kid}.")
        return key


def build_signing_provider(settings: AuthSettings) -> StaticKeyProvider:
    """Build the provider used to sign tokens."""
    return StaticKeyProvider(settings=settings)


def build_verification_provider(settings: AuthSettings) -> StaticKeyProvider | JWKSKeyProvider:
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
