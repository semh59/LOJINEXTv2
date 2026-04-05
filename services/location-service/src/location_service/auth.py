"""Bearer-token authentication helpers for Location Service."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header
from platform_auth import AuthSettings, TokenInvalidError, TokenMissingError, decode_bearer_token
from platform_auth.key_provider import build_verification_provider

from location_service.config import settings
from location_service.errors import location_auth_invalid, location_auth_required, location_forbidden

ROLE_ADMIN = "ADMIN"
ROLE_MANAGER = "MANAGER"
ROLE_SUPER_ADMIN = "SUPER_ADMIN"
ROLE_SERVICE = "SERVICE"
TRIP_SERVICE_NAME = "trip-service"


@dataclass(frozen=True)
class AuthContext:
    """Authenticated caller context used by routers."""

    actor_id: str
    role: str
    service_name: str | None = None


def _platform_auth_settings() -> AuthSettings:
    """Build shared auth settings for inbound token verification."""
    return AuthSettings(
        algorithm=settings.auth_jwt_algorithm,
        shared_secret=(
            settings.resolved_auth_jwt_secret if settings.auth_jwt_algorithm.upper().startswith("HS") else None
        ),
        issuer=settings.auth_issuer or None,
        audience=settings.auth_audience or None,
        public_key=settings.auth_public_key or None,
        private_key=settings.auth_private_key or None,
        jwks_url=settings.auth_jwks_url or None,
        jwks_cache_ttl_seconds=settings.auth_jwks_cache_ttl_seconds,
    )


def auth_verify_status() -> str:
    """Return `ok` when inbound auth config is locally coherent."""
    auth_settings = _platform_auth_settings()
    if auth_settings.uses_hmac and not auth_settings.shared_secret:
        return "fail"
    if auth_settings.uses_rsa:
        if not auth_settings.issuer or not auth_settings.audience:
            return "fail"
        if not auth_settings.public_key and not auth_settings.jwks_url:
            return "fail"
    try:
        build_verification_provider(auth_settings)
    except Exception:
        return "fail"
    return "ok"


def _decode_claims(authorization: str | None):
    """Decode Authorization header into normalized claims."""
    try:
        return decode_bearer_token(authorization, _platform_auth_settings())
    except TokenMissingError as exc:
        raise location_auth_required() from exc
    except TokenInvalidError as exc:  # pragma: no cover - exercised via router tests
        detail = str(exc).strip() or None
        raise location_auth_invalid(detail) from exc


def require_public_user_token(authorization: str | None) -> AuthContext:
    """Validate a user bearer token for public Location Service endpoints."""
    claims = _decode_claims(authorization)
    role = claims.role.strip()
    actor_id = claims.sub.strip()
    if role not in {ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPER_ADMIN} or not actor_id:
        raise location_forbidden("User token does not have an allowed admin role.")
    return AuthContext(actor_id=actor_id, role=role)


def require_super_admin_token(authorization: str | None) -> AuthContext:
    """Validate that the caller is a SUPER_ADMIN user."""
    auth = require_public_user_token(authorization)
    if auth.role != ROLE_SUPER_ADMIN:
        raise location_forbidden("This action requires the SUPER_ADMIN role.")
    return auth


def require_trip_service_token(authorization: str | None) -> AuthContext:
    """Validate the internal trip-service bearer token."""
    claims = _decode_claims(authorization)
    role = claims.role.strip()
    service_name = (claims.service or "").strip()
    actor_id = claims.sub.strip()
    if role != ROLE_SERVICE or not service_name or not actor_id:
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
