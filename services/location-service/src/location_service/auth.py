"""Bearer-token authentication helpers for Location Service."""

from __future__ import annotations

import httpx
from fastapi import Header
from platform_auth import (
    AuthContext,
    AuthSettings,
    PlatformRole,
    TokenClaims,
    TokenInvalidError,
    TokenMissingError,
    decode_bearer_token,
)
from platform_auth.key_provider import build_verification_provider

from location_service.config import settings
from location_service.errors import location_auth_invalid, location_auth_required, location_forbidden

TRIP_SERVICE_NAME = "trip-service"

_PUBLIC_USER_ROLES = {PlatformRole.MANAGER, PlatformRole.SUPER_ADMIN}


def _platform_auth_settings() -> AuthSettings:
    """Build shared auth settings for inbound token verification."""
    return AuthSettings(
        algorithm=settings.auth_jwt_algorithm,
        issuer=settings.auth_issuer or None,
        audience=settings.auth_audience or None,
        jwks_url=settings.auth_jwks_url or None,
        jwks_cache_ttl_seconds=settings.auth_jwks_cache_ttl_seconds,
    )


async def _probe_jwks_document(jwks_url: str) -> bool:
    """Return whether the configured JWKS endpoint serves a usable keys array."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(jwks_url)
            if response.status_code != 200:
                return False
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return False
    return isinstance(payload, dict) and isinstance(payload.get("keys"), list) and bool(payload["keys"])


async def auth_verify_status() -> str:
    """Return `ok` when inbound auth config is live and coherent."""
    auth_settings = _platform_auth_settings()
    if auth_settings.algorithm.upper() != "RS256":
        return "fail"
    if not auth_settings.issuer or not auth_settings.audience or not auth_settings.jwks_url:
        return "fail"
    if not await _probe_jwks_document(auth_settings.jwks_url):
        return "fail"
    try:
        build_verification_provider(auth_settings)
    except Exception:
        return "fail"
    return "ok"


def _decode_claims(authorization: str | None) -> TokenClaims:
    """Decode Authorization header into normalized claims."""
    try:
        return decode_bearer_token(authorization, _platform_auth_settings())
    except TokenMissingError as exc:
        raise location_auth_required() from exc
    except TokenInvalidError as exc:  # pragma: no cover - exercised via router tests
        detail = str(exc).strip() or "Invalid or expired token."
        raise location_auth_invalid(detail) from exc


def require_public_user_token(authorization: str | None) -> AuthContext:
    """Validate a user bearer token for public Location Service endpoints."""
    claims = _decode_claims(authorization)
    role = claims.role.strip()
    actor_id = claims.sub.strip()
    if role not in _PUBLIC_USER_ROLES or not actor_id:
        raise location_forbidden("User token does not have an allowed admin role.")
    return AuthContext(actor_id=actor_id, role=role)


def require_super_admin_token(authorization: str | None) -> AuthContext:
    """Validate that the caller is a SUPER_ADMIN user."""
    auth = require_public_user_token(authorization)
    if auth.role != PlatformRole.SUPER_ADMIN:
        raise location_forbidden("This action requires the SUPER_ADMIN role.")
    return auth


def require_trip_service_token(authorization: str | None) -> AuthContext:
    """Validate the internal trip-service bearer token."""
    claims = _decode_claims(authorization)
    role = claims.role.strip()
    service_name = (claims.service or "").strip()
    actor_id = claims.sub.strip()
    if role != PlatformRole.SERVICE or not service_name or not actor_id:
        raise location_forbidden("Token is not a valid service token.")
    if service_name != TRIP_SERVICE_NAME:
        raise location_forbidden("Service token is not allowed for this endpoint.")
    return AuthContext(actor_id=actor_id, role=role, service_name=service_name)


def user_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for public admin-authenticated endpoints."""
    return require_public_user_token(authorization)


def super_admin_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for public SUPER_ADMIN-only endpoints."""
    return require_super_admin_token(authorization)


def trip_service_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for Trip Service-owned internal endpoints."""
    return require_trip_service_token(authorization)
