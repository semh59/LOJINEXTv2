"""Bearer-token authentication helpers for driver-service (spec Section 8)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Header
from platform_auth import (
    AuthSettings,
    ServiceTokenAcquisitionError,
    ServiceTokenCache,
    TokenInvalidError,
    TokenMissingError,
    decode_bearer_token,
)
from platform_auth.key_provider import JWKSKeyProvider, build_verification_provider

from driver_service.config import settings
from driver_service.enums import ActorRole
from driver_service.errors import (
    driver_auth_invalid,
    driver_auth_required,
    driver_forbidden,
    driver_internal_auth_required,
    driver_internal_forbidden,
)

_ALLOWED_INTERNAL_SERVICES = {"driver-service", "fleet-service"}
_SERVICE_TOKEN_CACHE = ServiceTokenCache()


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
        return self.role == ActorRole.SERVICE


def _verification_auth_settings() -> AuthSettings:
    """Build shared auth settings for inbound RS256 verification."""
    return AuthSettings(
        algorithm=settings.auth_jwt_algorithm,
        issuer=settings.auth_issuer or None,
        audience=settings.auth_audience or None,
        jwks_url=settings.auth_jwks_url or None,
        jwks_cache_ttl_seconds=settings.auth_jwks_cache_ttl_seconds,
    )


def _service_token_audience(explicit_audience: str | None = None) -> str:
    """Return the canonical audience for outbound service tokens."""
    return explicit_audience or settings.auth_service_audience


def _outbound_token_request(*, audience: str | None = None) -> dict[str, str | None]:
    """Return outbound service-token request arguments."""
    return {
        "service_name": settings.service_name,
        "audience": _service_token_audience(audience),
        "token_url": settings.auth_service_token_url,
        "client_id": settings.auth_service_client_id,
        "client_secret": settings.auth_service_client_secret,
    }


def auth_verify_status() -> str:
    """Return `ok` when inbound RS256 verification can load JWKS material."""
    auth_settings = _verification_auth_settings()
    if auth_settings.algorithm.upper() != "RS256":
        return "fail"
    if not auth_settings.issuer or not auth_settings.audience or not auth_settings.jwks_url:
        return "fail"
    try:
        provider = build_verification_provider(auth_settings)
        if not isinstance(provider, JWKSKeyProvider):
            return "fail"
        provider._load_jwks()
    except Exception:
        return "fail"
    return "ok"


async def auth_outbound_status(*, audience: str | None = None) -> str:
    """Return `ok` when outbound service auth can acquire a token."""
    try:
        await _SERVICE_TOKEN_CACHE.get_token(**_outbound_token_request(audience=audience))
    except ServiceTokenAcquisitionError:
        return "fail"
    return "ok"


def _decode_claims(authorization: str | None) -> Any:
    """Decode Authorization header into normalized claims."""
    try:
        return decode_bearer_token(authorization, _verification_auth_settings())
    except TokenMissingError as exc:
        raise driver_auth_required() from exc
    except TokenInvalidError as exc:
        detail = str(exc).strip() or None
        raise driver_auth_invalid(detail) from exc
    except Exception as exc:
        # Fallback for unexpected JWT errors (e.g. InvalidKeyError from PyJWT)
        raise driver_auth_invalid(str(exc)) from exc


async def issue_internal_service_token(*, audience: str | None = None) -> str:
    """Return an outbound service token acquired from identity-service."""
    try:
        return await _SERVICE_TOKEN_CACHE.get_token(**_outbound_token_request(audience=audience))
    except ServiceTokenAcquisitionError as exc:
        raise RuntimeError(str(exc)) from exc


def require_admin_token(authorization: str | None) -> AuthContext:
    """Validate a bearer token requiring ADMIN role."""
    claims = _decode_claims(authorization)
    role = claims.role
    if role != ActorRole.ADMIN:
        raise driver_forbidden("Only ADMIN can perform this action.")
    actor_id = claims.sub.strip()
    if not actor_id:
        raise driver_auth_invalid("Token is missing sub.")
    return AuthContext(actor_id=actor_id, role=role)


def require_admin_or_manager_token(authorization: str | None) -> AuthContext:
    """Validate a bearer token requiring ADMIN or MANAGER role."""
    claims = _decode_claims(authorization)
    role = claims.role
    if role not in {ActorRole.ADMIN, ActorRole.MANAGER}:
        raise driver_forbidden("ADMIN or MANAGER role required.")
    actor_id = claims.sub.strip()
    if not actor_id:
        raise driver_auth_invalid("Token is missing sub.")
    return AuthContext(actor_id=actor_id, role=role)


def require_internal_service_token(authorization: str | None) -> AuthContext:
    """Validate a service bearer token for internal endpoints."""
    try:
        claims = decode_bearer_token(authorization, _verification_auth_settings())
    except TokenMissingError as exc:
        raise driver_internal_auth_required() from exc
    except TokenInvalidError as exc:
        detail = str(exc).strip() or "Invalid token."
        raise driver_auth_invalid(detail) from exc

    role = claims.role.strip()
    service_name = (claims.service or "").strip()
    actor_id = claims.sub.strip()
    if role != ActorRole.SERVICE or not service_name or not actor_id:
        raise driver_internal_forbidden("Token is not a valid service token.")
    if actor_id != service_name:
        raise driver_internal_forbidden("Service token subject must match service name.")
    if not service_name or service_name not in _ALLOWED_INTERNAL_SERVICES:
        raise driver_internal_forbidden("Service token is not allowed for driver internal endpoints.")
    return AuthContext(actor_id=actor_id, role=ActorRole.SERVICE, service_name=service_name)


def require_admin_or_internal_token(authorization: str | None) -> AuthContext:
    """Validate a bearer token requiring ADMIN or SERVICE role."""
    claims = _decode_claims(authorization)
    role = claims.role.strip()
    actor_id = claims.sub.strip()
    if not actor_id:
        raise driver_auth_invalid("Token is missing sub.")
    if role == ActorRole.ADMIN:
        return AuthContext(actor_id=actor_id, role=role)
    service_name = (claims.service or "").strip()
    if role == ActorRole.SERVICE:
        if not service_name or service_name != actor_id:
            raise driver_forbidden("Service token subject must match service name.")
        if service_name not in _ALLOWED_INTERNAL_SERVICES:
            raise driver_forbidden("Service token is not allowed for this endpoint.")
        return AuthContext(actor_id=actor_id, role=ActorRole.SERVICE, service_name=service_name)
    raise driver_forbidden("ADMIN or internal service role required.")


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
