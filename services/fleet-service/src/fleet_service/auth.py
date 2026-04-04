"""JWT authentication for Fleet Service (Section 8 auth model).

Auth model:
- ADMIN/SUPER_ADMIN: public /api/v1/* endpoints
- SUPER_ADMIN only: hard-delete
- SERVICE: internal /internal/v1/* endpoints
- role mismatch: 403 INSUFFICIENT_ROLE or UNAUTHORIZED_INTERNAL_CALL
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Header

from fleet_service.config import settings
from fleet_service.domain.enums import ActorType
from fleet_service.errors import ProblemDetailError

# --- Auth errors (401/403) ---


class AuthRequiredError(ProblemDetailError):
    """Authorization header is missing."""

    def __init__(self) -> None:
        super().__init__(401, "AUTH_REQUIRED", "Authorization header is required")


class AuthInvalidError(ProblemDetailError):
    """JWT token is invalid or expired."""

    def __init__(self, detail: str = "Invalid or expired token") -> None:
        super().__init__(401, "AUTH_INVALID", detail)


# --- AuthContext ---


@dataclass(frozen=True)
class AuthContext:
    """Authenticated caller context for request processing."""

    actor_id: str
    actor_type: str  # ActorType value
    service_name: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.actor_type == ActorType.ADMIN

    @property
    def is_super_admin(self) -> bool:
        return self.actor_type == ActorType.SUPER_ADMIN

    @property
    def is_service(self) -> bool:
        return self.actor_type == ActorType.SERVICE


# --- Token decode ---


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
        raise AuthInvalidError() from exc
    if not isinstance(payload, dict):
        raise AuthInvalidError()
    return payload


def _parse_authorization_header(authorization: str | None) -> str:
    """Extract the bearer token from the Authorization header."""
    if not authorization:
        raise AuthRequiredError()
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        raise AuthInvalidError("Authorization header must use the Bearer scheme.")
    return value


# --- Public (admin) endpoints ---


def require_admin_token(authorization: str | None) -> AuthContext:
    """Validate a bearer token requiring ADMIN or SUPER_ADMIN role."""
    from fleet_service.errors import InsufficientRoleError

    payload = _decode_token(_parse_authorization_header(authorization))
    role = str(payload.get("role", ""))
    if role not in {ActorType.ADMIN, ActorType.SUPER_ADMIN}:
        raise InsufficientRoleError("ADMIN")
    actor_id = str(payload.get("sub", "")).strip()
    if not actor_id:
        raise AuthInvalidError("Token is missing sub.")
    return AuthContext(actor_id=actor_id, actor_type=role)


def require_super_admin_token(authorization: str | None) -> AuthContext:
    """Validate a bearer token requiring SUPER_ADMIN role (hard-delete only)."""
    from fleet_service.errors import InsufficientRoleError

    payload = _decode_token(_parse_authorization_header(authorization))
    role = str(payload.get("role", ""))
    if role != ActorType.SUPER_ADMIN:
        raise InsufficientRoleError("SUPER_ADMIN")
    actor_id = str(payload.get("sub", "")).strip()
    if not actor_id:
        raise AuthInvalidError("Token is missing sub.")
    return AuthContext(actor_id=actor_id, actor_type=role)


# --- Internal (service) endpoints ---


def require_service_token(authorization: str | None) -> AuthContext:
    """Validate a service bearer token for internal endpoints."""
    from fleet_service.errors import UnauthorizedInternalCallError

    payload = _decode_token(_parse_authorization_header(authorization))
    role = str(payload.get("role", ""))
    actor_id = str(payload.get("sub", "")).strip()
    service_name = str(payload.get("service", "")).strip()
    if role != ActorType.SERVICE or not actor_id:
        raise UnauthorizedInternalCallError()
    return AuthContext(actor_id=actor_id, actor_type=ActorType.SERVICE, service_name=service_name)


# --- FastAPI Dependencies ---


def admin_auth(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for ADMIN/SUPER_ADMIN endpoints."""
    return require_admin_token(authorization)


def super_admin_auth(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for SUPER_ADMIN-only endpoints (hard-delete)."""
    return require_super_admin_token(authorization)


def service_auth(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for internal SERVICE endpoints."""
    return require_service_token(authorization)


# --- Outbound JWT signing ---


def sign_service_token(target_secret: str, target_name: str = "fleet-to-target") -> str:
    """Generate a JWT token for outbound service-to-service calls.

    Args:
        target_secret: The JWT secret shared with the target service.
        target_name: Name for logging/debugging.

    Returns:
        Signed JWT string with 5-minute expiry.
    """
    now = int(time.time())
    payload = {
        "sub": "fleet-service",
        "role": ActorType.SERVICE,
        "service": settings.service_name,
        "iat": now,
        "exp": now + 300,
    }
    return jwt.encode(payload, target_secret, algorithm=settings.auth_jwt_algorithm)
