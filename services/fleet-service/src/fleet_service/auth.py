"""JWT authentication for Fleet Service (Section 8 auth model).

Auth model:
- ADMIN/SUPER_ADMIN: public /api/v1/* endpoints
- SUPER_ADMIN only: hard-delete
- SERVICE: internal /internal/v1/* endpoints
- role mismatch: 403 INSUFFICIENT_ROLE or UNAUTHORIZED_INTERNAL_CALL
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header
from platform_auth import (
    AuthSettings,
    ServiceTokenAcquisitionError,
    ServiceTokenCache,
    TokenInvalidError,
    TokenMissingError,
    decode_bearer_token,
)
from platform_auth.token_factory import ServiceTokenFactory
from platform_auth.key_provider import build_verification_provider

from fleet_service.config import settings
from fleet_service.domain.enums import ActorType
from fleet_service.errors import ProblemDetailError

_TRIP_SERVICE_ALLOWLIST = {"trip-service"}
_SERVICE_TOKEN_CACHE = ServiceTokenCache()
_DEFAULT_SERVICE_AUDIENCE = "lojinext-platform"


class AuthRequiredError(ProblemDetailError):
    """Authorization header is missing."""

    def __init__(self) -> None:
        super().__init__(401, "AUTH_REQUIRED", "Authorization header is required")


class AuthInvalidError(ProblemDetailError):
    """JWT token is invalid or expired."""

    def __init__(self, detail: str = "Invalid or expired token") -> None:
        super().__init__(401, "AUTH_INVALID", detail)


@dataclass(frozen=True)
class AuthContext:
    """Authenticated caller context for request processing."""

    actor_id: str
    actor_type: str
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


def _platform_auth_settings(*, audience: str | None = None) -> AuthSettings:
    """Build shared auth settings for inbound verification and outbound signing."""
    effective_audience = settings.auth_audience or audience or None
    return AuthSettings(
        algorithm=settings.auth_jwt_algorithm,
        shared_secret=settings.resolved_auth_jwt_secret if settings.auth_jwt_algorithm.upper().startswith("HS") else None,
        issuer=settings.auth_issuer or None,
        audience=effective_audience,
        public_key=settings.auth_public_key or None,
        private_key=settings.auth_private_key or None,
        jwks_url=settings.auth_jwks_url or None,
        jwks_cache_ttl_seconds=settings.auth_jwks_cache_ttl_seconds,
    )


def _service_token_audience(explicit_audience: str | None = None) -> str:
    """Return the canonical audience for outbound service tokens."""
    del explicit_audience
    return settings.auth_audience or _DEFAULT_SERVICE_AUDIENCE


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


def auth_outbound_status(*, audience: str | None = None) -> str:
    """Return `cold`, `ok`, or `fail` for outbound auth readiness."""
    auth_settings = _platform_auth_settings(audience=_service_token_audience(audience))
    if auth_settings.uses_hmac or auth_settings.private_key:
        return "ok"
    return _SERVICE_TOKEN_CACHE.readiness_state(
        service_name=settings.service_name,
        audience=auth_settings.audience if isinstance(auth_settings.audience, str) else None,
        token_url=settings.auth_service_token_url,
        client_id=settings.auth_service_client_id,
        client_secret=settings.auth_service_client_secret,
    )


def _decode_claims(authorization: str | None):
    """Decode Authorization header into normalized claims."""
    try:
        return decode_bearer_token(authorization, _platform_auth_settings())
    except TokenMissingError as exc:
        raise AuthRequiredError() from exc
    except TokenInvalidError as exc:
        detail = str(exc).strip() or "Invalid or expired token"
        raise AuthInvalidError(detail) from exc


def sign_service_token(target_secret: str, target_name: str = "fleet-to-target") -> str:
    """Generate a locally signed JWT token for outbound service-to-service calls."""
    del target_secret, target_name
    factory = ServiceTokenFactory(service_name=settings.service_name, settings=_platform_auth_settings())
    return factory.issue()


async def issue_service_token(*, audience: str | None = None) -> str:
    """Return an outbound service token for dependency calls."""
    auth_settings = _platform_auth_settings(audience=_service_token_audience(audience))
    if auth_settings.uses_hmac or auth_settings.private_key:
        factory = ServiceTokenFactory(service_name=settings.service_name, settings=auth_settings)
        return factory.issue()

    try:
        return await _SERVICE_TOKEN_CACHE.get_token(
            service_name=settings.service_name,
            audience=auth_settings.audience if isinstance(auth_settings.audience, str) else None,
            token_url=settings.auth_service_token_url,
            client_id=settings.auth_service_client_id,
            client_secret=settings.auth_service_client_secret,
        )
    except ServiceTokenAcquisitionError as exc:
        raise RuntimeError(str(exc)) from exc


def require_admin_token(authorization: str | None) -> AuthContext:
    """Validate a bearer token requiring ADMIN or SUPER_ADMIN role."""
    from fleet_service.errors import InsufficientRoleError

    claims = _decode_claims(authorization)
    role = claims.role
    if role not in {ActorType.ADMIN, ActorType.SUPER_ADMIN}:
        raise InsufficientRoleError("ADMIN")
    actor_id = claims.sub.strip()
    if not actor_id:
        raise AuthInvalidError("Token is missing sub.")
    return AuthContext(actor_id=actor_id, actor_type=role)


def require_super_admin_token(authorization: str | None) -> AuthContext:
    """Validate a bearer token requiring SUPER_ADMIN role (hard-delete only)."""
    from fleet_service.errors import InsufficientRoleError

    claims = _decode_claims(authorization)
    role = claims.role
    if role != ActorType.SUPER_ADMIN:
        raise InsufficientRoleError("SUPER_ADMIN")
    actor_id = claims.sub.strip()
    if not actor_id:
        raise AuthInvalidError("Token is missing sub.")
    return AuthContext(actor_id=actor_id, actor_type=role)


def require_service_token(authorization: str | None, *, allowed_services: set[str] | None = None) -> AuthContext:
    """Validate a service bearer token for internal endpoints."""
    from fleet_service.errors import UnauthorizedInternalCallError

    claims = _decode_claims(authorization)
    role = claims.role
    actor_id = claims.sub.strip()
    service_name = (claims.service or "").strip()
    if role != ActorType.SERVICE or not actor_id or not service_name:
        raise UnauthorizedInternalCallError()
    if allowed_services is not None and service_name not in allowed_services:
        raise UnauthorizedInternalCallError()
    return AuthContext(actor_id=actor_id, actor_type=ActorType.SERVICE, service_name=service_name)


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


def trip_service_auth(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for Trip-owned Fleet internal endpoints."""
    return require_service_token(authorization, allowed_services=_TRIP_SERVICE_ALLOWLIST)
