"""Bearer-token authentication helpers for Location Service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Header

from location_service.config import settings
from location_service.errors import location_auth_invalid, location_auth_required, location_forbidden

ROLE_ADMIN = "ADMIN"
ROLE_SUPER_ADMIN = "SUPER_ADMIN"
ROLE_SERVICE = "SERVICE"
TRIP_SERVICE_NAME = "trip-service"


@dataclass(frozen=True)
class AuthContext:
    """Authenticated caller context used by routers."""

    actor_id: str
    role: str
    service_name: str | None = None


def _decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[settings.auth_jwt_algorithm],
            options={"require": ["sub", "role"]},
        )
    except jwt.PyJWTError as exc:  # pragma: no cover - exercised via router tests
        raise location_auth_invalid() from exc
    if not isinstance(payload, dict):
        raise location_auth_invalid()
    return payload


def _parse_authorization_header(authorization: str | None) -> str:
    """Extract the bearer token from the Authorization header."""
    if not authorization:
        raise location_auth_required()
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        raise location_auth_invalid("Authorization header must use the Bearer scheme.")
    return value


def require_public_user_token(authorization: str | None) -> AuthContext:
    """Validate a user bearer token for public Location Service endpoints."""
    payload = _decode_token(_parse_authorization_header(authorization))
    role = str(payload.get("role", "")).strip()
    actor_id = str(payload.get("sub", "")).strip()
    if role not in {ROLE_ADMIN, ROLE_SUPER_ADMIN} or not actor_id:
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
    payload = _decode_token(_parse_authorization_header(authorization))
    role = str(payload.get("role", "")).strip()
    service_name = str(payload.get("service", "")).strip()
    actor_id = str(payload.get("sub", "")).strip()
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
