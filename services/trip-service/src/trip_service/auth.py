"""Bearer-token authentication helpers for trip-service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Header

from trip_service.config import settings
from trip_service.enums import ActorType
from trip_service.errors import trip_auth_invalid, trip_auth_required, trip_forbidden, trip_validation_error


@dataclass(frozen=True)
class AuthContext:
    """Authenticated caller context used by routers."""

    actor_id: str
    actor_type: str
    role: str
    service_name: str | None = None

    @property
    def is_super_admin(self) -> bool:
        """Return whether the caller is a super admin."""
        return self.role == ActorType.SUPER_ADMIN


def _decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[settings.auth_jwt_algorithm],
            options={"require": ["sub", "role"]},
        )
    except jwt.PyJWTError as exc:  # pragma: no cover - exercised through router tests
        raise trip_auth_invalid() from exc
    if not isinstance(payload, dict):
        raise trip_auth_invalid()
    return payload


def _parse_authorization_header(authorization: str | None) -> str:
    """Extract the bearer token from the Authorization header."""
    if not authorization:
        raise trip_auth_required()
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        raise trip_auth_invalid("Authorization header must use the Bearer scheme.")
    return value


def _legacy_header_context(x_actor_type: str | None, x_actor_id: str | None) -> AuthContext:
    """Build an auth context from legacy headers when compatibility is enabled."""
    if not settings.allow_legacy_actor_headers:
        raise trip_auth_required()
    if not x_actor_type or not x_actor_id:
        raise trip_auth_required()
    if x_actor_type not in {ActorType.ADMIN, ActorType.SUPER_ADMIN}:
        raise trip_validation_error(
            "Request validation failed.",
            errors=[{"field": "header.X-Actor-Type", "message": "Legacy actor type must be ADMIN or SUPER_ADMIN."}],
        )
    return AuthContext(actor_id=x_actor_id, actor_type=x_actor_type, role=x_actor_type)


def require_user_token(
    authorization: str | None,
    x_actor_type: str | None = None,
    x_actor_id: str | None = None,
) -> AuthContext:
    """Validate a user bearer token and return the caller context."""
    if authorization is None:
        return _legacy_header_context(x_actor_type, x_actor_id)

    payload = _decode_token(_parse_authorization_header(authorization))
    role = str(payload.get("role", ""))
    if role not in {ActorType.ADMIN, ActorType.SUPER_ADMIN}:
        raise trip_forbidden("User token does not have an admin role.")
    actor_id = str(payload.get("sub", "")).strip()
    if not actor_id:
        raise trip_auth_invalid("Token is missing sub.")
    return AuthContext(actor_id=actor_id, actor_type=role, role=role)


def require_service_token(authorization: str | None, allowed_services: set[str]) -> AuthContext:
    """Validate a service bearer token and enforce the allowed service names."""
    payload = _decode_token(_parse_authorization_header(authorization))
    role = str(payload.get("role", ""))
    service_name = str(payload.get("service", "")).strip()
    actor_id = str(payload.get("sub", "")).strip()
    if role != ActorType.SERVICE or not service_name or not actor_id:
        raise trip_forbidden("Token is not a valid service token.")
    if service_name not in allowed_services:
        raise trip_forbidden("Service token is not allowed for this endpoint.")
    return AuthContext(actor_id=actor_id, actor_type=ActorType.SERVICE, role=role, service_name=service_name)


def user_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
    x_actor_type: str | None = Header(None, alias="X-Actor-Type"),
    x_actor_id: str | None = Header(None, alias="X-Actor-Id"),
) -> AuthContext:
    """FastAPI dependency for public user-authenticated endpoints."""
    return require_user_token(authorization, x_actor_type, x_actor_id)


def telegram_service_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for Telegram-owned internal endpoints."""
    return require_service_token(authorization, {"telegram-service"})


def excel_service_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for Excel-owned internal endpoints."""
    return require_service_token(authorization, {"excel-service"})


def admin_or_internal_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
    x_actor_type: str | None = Header(None, alias="X-Actor-Type"),
    x_actor_id: str | None = Header(None, alias="X-Actor-Id"),
) -> AuthContext:
    """FastAPI dependency for ADMIN or internal service endpoints."""
    if authorization is None:
        return _legacy_header_context(x_actor_type, x_actor_id)

    payload = _decode_token(_parse_authorization_header(authorization))
    role = str(payload.get("role", ""))
    if role in {ActorType.ADMIN, ActorType.SUPER_ADMIN}:
        actor_id = str(payload.get("sub", "")).strip()
        return AuthContext(actor_id=actor_id, actor_type=role, role=role)

    # Fallback to service token check
    service_name = str(payload.get("service", "")).strip()
    if role == ActorType.SERVICE and service_name:
        actor_id = str(payload.get("sub", "")).strip()
        return AuthContext(actor_id=actor_id, actor_type=role, role=role, service_name=service_name)

    raise trip_forbidden("ADMIN or internal service role required.")
