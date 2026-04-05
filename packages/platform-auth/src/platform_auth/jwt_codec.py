"""JWT encode/decode helpers."""

from __future__ import annotations

from typing import Any, Mapping

import jwt

from platform_auth.claims import TokenClaims
from platform_auth.errors import PlatformAuthError, TokenInvalidError
from platform_auth.key_provider import build_signing_provider, build_verification_provider
from platform_auth.settings import AuthSettings


def issue_token(
    payload: Mapping[str, Any],
    settings: AuthSettings,
    *,
    headers: Mapping[str, Any] | None = None,
) -> str:
    """Issue a JWT using the configured signing mechanism."""
    provider = build_signing_provider(settings)
    token_headers = dict(headers or {})
    return jwt.encode(
        dict(payload),
        provider.signing_key(),
        algorithm=settings.algorithm,
        headers=token_headers or None,
    )


def verify_token(
    token: str,
    settings: AuthSettings,
    *,
    required_claims: tuple[str, ...] = ("sub", "role"),
) -> TokenClaims:
    """Verify a JWT and return normalized claims."""
    try:
        header = jwt.get_unverified_header(token)
        provider = build_verification_provider(settings)
        options = {"require": list(required_claims)}
        payload = jwt.decode(
            token,
            provider.verification_key(header),
            algorithms=[settings.algorithm],
            issuer=settings.issuer or None,
            audience=settings.normalized_audience(),
            options=options,
        )
    except PlatformAuthError:
        raise
    except jwt.PyJWTError as exc:
        raise TokenInvalidError(str(exc) or "Invalid token.") from exc
    if not isinstance(payload, dict):
        raise TokenInvalidError("Decoded token payload was not an object.")
    return TokenClaims.from_payload(payload, header=header)
