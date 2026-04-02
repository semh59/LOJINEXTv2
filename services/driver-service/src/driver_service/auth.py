"""Bearer-token authentication helpers for driver-service (spec Section 8)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Header

from driver_service.config import settings
from driver_service.enums import ActorRole
from driver_service.errors import (
    driver_auth_invalid,
    driver_auth_required,
    driver_forbidden,
    driver_internal_auth_required,
    driver_internal_forbidden,
)


@dataclass(frozen=True)
class AuthContext:
    """Authenticated caller context used by routers."""

    actor_id: str
    role: str
    service_name: str | None = None

    @property
    def is_admin(self) -> bool:
        """Return whether the caller has ADMIN role."""
        return self.role == ActorRole.ADMIN

    @property
    def is_manager(self) -> bool:
        """Return whether the caller has MANAGER role."""
        return self.role == ActorRole.MANAGER

    @property
    def is_internal_service(self) -> bool:
        """Return whether the caller is an internal service."""
        return self.role in {ActorRole.INTERNAL_SERVICE, ActorRole.SERVICE}


def _decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[settings.auth_jwt_algorithm],
            options={"require": ["sub", "role"]},
        )
    except jwt.PyJWTError as exc:
        raise driver_auth_invalid() from exc
    if not isinstance(payload, dict):
        raise driver_auth_invalid()
    return payload


def _parse_authorization_header(authorization: str | None) -> str:
    """Extract the bearer token from the Authorization header."""
    if not authorization:
        raise driver_auth_required()
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        raise driver_auth_invalid("Authorization header must use the Bearer scheme.")
    return value


# ---- Public admin/manager endpoints ----


def require_admin_token(authorization: str | None) -> AuthContext:
    """Validate a bearer token requiring ADMIN role."""
    payload = _decode_token(_parse_authorization_header(authorization))
    role = str(payload.get("role", ""))
    if role != ActorRole.ADMIN:
        raise driver_forbidden("Only ADMIN can perform this action.")
    actor_id = str(payload.get("sub", "")).strip()
    if not actor_id:
        raise driver_auth_invalid("Token is missing sub.")
    return AuthContext(actor_id=actor_id, role=role)


def require_admin_or_manager_token(authorization: str | None) -> AuthContext:
    """Validate a bearer token requiring ADMIN or MANAGER role."""
    payload = _decode_token(_parse_authorization_header(authorization))
    role = str(payload.get("role", ""))
    if role not in {ActorRole.ADMIN, ActorRole.MANAGER}:
        raise driver_forbidden("ADMIN or MANAGER role required.")
    actor_id = str(payload.get("sub", "")).strip()
    if not actor_id:
        raise driver_auth_invalid("Token is missing sub.")
    return AuthContext(actor_id=actor_id, role=role)


# ---- Internal service endpoints ----


def require_internal_service_token(authorization: str | None) -> AuthContext:
    """Validate a service bearer token for internal endpoints."""
    if not authorization:
        raise driver_internal_auth_required()
    payload = _decode_token(_parse_authorization_header(authorization))
    role = str(payload.get("role", ""))
    service_name = str(payload.get("service", "")).strip()
    actor_id = str(payload.get("sub", "")).strip()
    if role not in {ActorRole.SERVICE, ActorRole.INTERNAL_SERVICE} or not actor_id:
        raise driver_internal_forbidden("Token is not a valid service token.")
    return AuthContext(actor_id=actor_id, role=ActorRole.INTERNAL_SERVICE, service_name=service_name)


def require_admin_or_internal_token(authorization: str | None) -> AuthContext:
    """Validate a bearer token requiring ADMIN or INTERNAL_SERVICE role."""
    payload = _decode_token(_parse_authorization_header(authorization))
    role = str(payload.get("role", ""))
    actor_id = str(payload.get("sub", "")).strip()
    if not actor_id:
        raise driver_auth_invalid("Token is missing sub.")
    if role == ActorRole.ADMIN:
        return AuthContext(actor_id=actor_id, role=role)
    service_name = str(payload.get("service", "")).strip()
    if role in {ActorRole.SERVICE, ActorRole.INTERNAL_SERVICE}:
        return AuthContext(actor_id=actor_id, role=ActorRole.INTERNAL_SERVICE, service_name=service_name)
    raise driver_forbidden("ADMIN or internal service role required.")


# ---- FastAPI dependencies ----


def admin_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for ADMIN-only endpoints."""
    return require_admin_token(authorization)


def admin_or_manager_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for ADMIN + MANAGER endpoints."""
    return require_admin_or_manager_token(authorization)


def internal_service_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for internal service endpoints."""
    return require_internal_service_token(authorization)


def admin_or_internal_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for ADMIN or internal service endpoints."""
    return require_admin_or_internal_token(authorization)


def generate_internal_service_token() -> str:
    """Generate a JWT token for internal service-to-service calls."""
    import time

    now = int(time.time())
    payload = {
        "sub": "driver-service-internal",
        "role": ActorRole.INTERNAL_SERVICE,
        "service": settings.service_name,
        "iat": now,
        "exp": now + 300,  # 5 minutes
    }
    return jwt.encode(
        payload,
        settings.auth_jwt_secret,
        algorithm=settings.auth_jwt_algorithm,
    )
