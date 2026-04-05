"""Bearer-token authentication helpers for trip-service."""

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

from trip_service.config import settings
from trip_service.enums import ActorType
from trip_service.errors import trip_auth_invalid, trip_auth_required, trip_forbidden, trip_validation_error

_SERVICE_TOKEN_CACHE = ServiceTokenCache()
_DEFAULT_SERVICE_AUDIENCE = "lojinext-platform"


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


def _platform_auth_settings(*, audience: str | None = None) -> AuthSettings:
    """Build shared auth settings for inbound or outbound token handling."""
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
    """Return `ok` when inbound auth settings are locally coherent."""
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
    """Decode an Authorization header into normalized claims."""
    try:
        return decode_bearer_token(authorization, _platform_auth_settings())
    except TokenMissingError as exc:
        raise trip_auth_required() from exc
    except TokenInvalidError as exc:  # pragma: no cover - exercised through router tests
        detail = str(exc).strip() or None
        raise trip_auth_invalid(detail) from exc


async def issue_internal_service_token(*, audience: str | None = None) -> str:
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

    claims = _decode_claims(authorization)
    role = claims.role
    if role not in {ActorType.ADMIN, ActorType.SUPER_ADMIN}:
        raise trip_forbidden("User token does not have an admin role.")
    actor_id = claims.sub.strip()
    if not actor_id:
        raise trip_auth_invalid("Token is missing sub.")
    return AuthContext(actor_id=actor_id, actor_type=role, role=role)


def require_service_token(authorization: str | None, allowed_services: set[str]) -> AuthContext:
    """Validate a service bearer token and enforce the allowed service names."""
    claims = _decode_claims(authorization)
    role = claims.role
    service_name = (claims.service or "").strip()
    actor_id = claims.sub.strip()
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


def reference_service_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for service-only trip reference checks."""
    return require_service_token(authorization, {"driver-service", "fleet-service"})


def admin_or_internal_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
    x_actor_type: str | None = Header(None, alias="X-Actor-Type"),
    x_actor_id: str | None = Header(None, alias="X-Actor-Id"),
) -> AuthContext:
    """FastAPI dependency for ADMIN or internal service endpoints."""
    if authorization is None:
        return _legacy_header_context(x_actor_type, x_actor_id)

    claims = _decode_claims(authorization)
    role = claims.role
    if role in {ActorType.ADMIN, ActorType.SUPER_ADMIN}:
        actor_id = claims.sub.strip()
        return AuthContext(actor_id=actor_id, actor_type=role, role=role)

    service_name = (claims.service or "").strip()
    if role == ActorType.SERVICE and service_name:
        actor_id = claims.sub.strip()
        return AuthContext(actor_id=actor_id, actor_type=role, role=role, service_name=service_name)

    raise trip_forbidden("ADMIN or internal service role required.")
