"""Header parsing helpers shared across service adapters."""

from __future__ import annotations

from platform_auth.claims import TokenClaims
from platform_auth.errors import TokenInvalidError, TokenMissingError
from platform_auth.jwt_codec import async_verify_token, verify_token
from platform_auth.settings import AuthSettings


def parse_bearer_token(authorization: str | None) -> str:
    """Extract a bearer token from the Authorization header."""
    if not authorization:
        raise TokenMissingError("Authorization header is required.")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        raise TokenInvalidError("Authorization header must use the Bearer scheme.")
    return value


async def async_decode_bearer_token(
    authorization: str | None, settings: AuthSettings
) -> TokenClaims:
    """Decode a bearer token asynchronously using the shared codec."""
    return await async_verify_token(parse_bearer_token(authorization), settings)


def decode_bearer_token(
    authorization: str | None, settings: AuthSettings
) -> TokenClaims:
    """Decode a bearer token using the shared codec (synchronously)."""
    return verify_token(parse_bearer_token(authorization), settings)
