"""Bearer-token authentication helpers for driver-service (spec Section 8)."""

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
from platform_auth.key_provider import build_verification_provider
from platform_auth.token_factory import ServiceTokenFactory

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
_DEFAULT_SERVICE_AUDIENCE = "lojinext-platform"


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


def _platform_auth_settings(*, audience: str | None = None) -> AuthSettings:
    """Build shared auth settings for inbound verification and outbound signing."""
    effective_audience = settings.auth_audience or audience or None
    return AuthSettings(
        algorithm=settings.auth_jwt_algorithm,
        shared_secret=(
            settings.resolved_auth_jwt_secret if settings.auth_jwt_algorithm.upper().startswith("HS") else None
        ),
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
        raise driver_auth_required() from exc
    except TokenInvalidError as exc:
        detail = str(exc).strip() or None
        raise driver_auth_invalid(detail) from exc


def _issue_local_service_token(*, audience: str | None = None) -> str:
    """Issue a locally signed service token when shared-secret signing is allowed."""
    auth_settings = _platform_auth_settings(audience=_service_token_audience(audience))
    factory = ServiceTokenFactory(service_name=settings.service_name, settings=auth_settings)
    return factory.issue()


async def issue_internal_service_token(*, audience: str | None = None) -> str:
    """Return an outbound service token for Trip-bound maintenance calls."""
    auth_settings = _platform_auth_settings(audience=_service_token_audience(audience))
    if auth_settings.uses_hmac or auth_settings.private_key:
        return _issue_local_service_token(audience=audience)

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
        claims = decode_bearer_token(authorization, _platform_auth_settings())
    except TokenMissingError as exc:
        raise driver_internal_auth_required() from exc
    except TokenInvalidError as exc:
        detail = str(exc).strip() or "Invalid token."
        raise driver_auth_invalid(detail) from exc

    role = claims.role
    service_name = (claims.service or "").strip()
    actor_id = claims.sub.strip()
    if role not in {ActorRole.SERVICE, ActorRole.INTERNAL_SERVICE} or not actor_id:
        raise driver_internal_forbidden("Token is not a valid service token.")
    if not service_name or service_name not in _ALLOWED_INTERNAL_SERVICES:
        raise driver_internal_forbidden("Service token is not allowed for driver internal endpoints.")
    return AuthContext(actor_id=actor_id, role=ActorRole.INTERNAL_SERVICE, service_name=service_name)


def require_admin_or_internal_token(authorization: str | None) -> AuthContext:
    """Validate a bearer token requiring ADMIN or INTERNAL_SERVICE role."""
    claims = _decode_claims(authorization)
    role = claims.role
    actor_id = claims.sub.strip()
    if not actor_id:
        raise driver_auth_invalid("Token is missing sub.")
    if role == ActorRole.ADMIN:
        return AuthContext(actor_id=actor_id, role=role)
    service_name = (claims.service or "").strip()
    if role in {ActorRole.SERVICE, ActorRole.INTERNAL_SERVICE}:
        if not service_name or service_name not in _ALLOWED_INTERNAL_SERVICES:
            raise driver_forbidden("Service token is not allowed for this endpoint.")
        return AuthContext(actor_id=actor_id, role=ActorRole.INTERNAL_SERVICE, service_name=service_name)
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


def generate_internal_service_token() -> str:
    """Generate a locally signed internal service token for HS256 recovery paths."""
    return _issue_local_service_token()
