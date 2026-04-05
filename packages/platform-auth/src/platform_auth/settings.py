"""Configuration object for shared auth helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthSettings:
    """Static auth configuration consumed by the shared JWT helpers."""

    algorithm: str = "HS256"
    shared_secret: str | None = None
    issuer: str | None = None
    audience: str | tuple[str, ...] | None = None
    public_key: str | None = None
    private_key: str | None = None
    jwks_url: str | None = None
    jwks_cache_ttl_seconds: int = 300

    def normalized_audience(self) -> str | list[str] | None:
        """Return a PyJWT-compatible audience value."""
        if self.audience is None:
            return None
        if isinstance(self.audience, tuple):
            return list(self.audience)
        return self.audience

    @property
    def uses_hmac(self) -> bool:
        """Return whether the configured algorithm is HMAC-based."""
        return self.algorithm.upper().startswith("HS")

    @property
    def uses_rsa(self) -> bool:
        """Return whether the configured algorithm is RSA-based."""
        return self.algorithm.upper().startswith("RS")
