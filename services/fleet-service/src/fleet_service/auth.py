"""JWT authentication for Fleet Service (Section 8 auth model).

Auth model:
- ADMIN/SUPER_ADMIN: public /api/v1/* endpoints
- SUPER_ADMIN only: hard-delete
- SERVICE: internal /internal/v1/* endpoints
- role mismatch: 403 INSUFFICIENT_ROLE or UNAUTHORIZED_INTERNAL_CALL
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from fastapi import Header

from fleet_service.config import settings
from fleet_service.errors import ProblemDetailError
from platform_auth import (
    AuthContext,
    AuthSettings,
    PlatformRole,
    ServiceTokenAcquisitionError,
    ServiceTokenCache,
    TokenInvalidError,
    TokenMissingError,
    decode_bearer_token,
)
from platform_auth.key_provider import build_verification_provider

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


def _platform_auth_settings(*, audience: str | None = None) -> AuthSettings:
    """Build shared auth settings for inbound verification and outbound tokens.

    Implements [2026-04-05] Recovery auth bridge fallback to PLATFORM_JWT_SECRET.
    """
    effective_audience = audience or settings.auth_audience or None

    fallback_secret = getattr(settings, "platform_jwt_secret", None)
    if fallback_secret and settings.environment != "prod":
        return AuthSettings(
            algorithm="HS256",
            shared_secret=fallback_secret,
            issuer=settings.auth_issuer or None,
            audience=effective_audience,
            jwks_url=None,
        )

    return AuthSettings(
        algorithm=settings.auth_jwt_algorithm,
        issuer=settings.auth_issuer or None,
        audience=effective_audience,
        jwks_url=settings.auth_jwks_url or None,
        jwks_cache_ttl_seconds=settings.auth_jwks_cache_ttl_seconds,
    )


def _service_token_audience(explicit_audience: str | None = None) -> str:
    """Return the canonical audience for outbound service tokens."""
    return explicit_audience or settings.auth_audience or _DEFAULT_SERVICE_AUDIENCE


def _probe_jwks_document(jwks_url: str) -> bool:
    """Return whether the configured JWKS endpoint serves a usable keys array."""
    request = urllib.request.Request(jwks_url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return False
    return isinstance(payload, dict) and isinstance(payload.get("keys"), list) and bool(payload["keys"])


def auth_verify_status() -> str:
    """Return `ok` when inbound auth config is live and coherent."""
    auth_settings = _platform_auth_settings()
    if auth_settings.algorithm.upper() != "RS256":
        return "fail"
    if not auth_settings.issuer or not auth_settings.audience or not auth_settings.jwks_url:
        return "fail"
    if not _probe_jwks_document(auth_settings.jwks_url):
        return "fail"
    try:
        build_verification_provider(auth_settings)
    except Exception:
        return "fail"
    return "ok"


async def auth_outbound_status(*, audience: str | None = None) -> str:
    """Return `ok` or `fail` for outbound auth readiness."""
    auth_settings = _platform_auth_settings(audience=_service_token_audience(audience))
    try:
        await _SERVICE_TOKEN_CACHE.get_token(
            service_name=settings.service_name,
            audience=auth_settings.audience if isinstance(auth_settings.audience, str) else None,
            token_url=settings.auth_service_token_url,
            client_id=settings.auth_service_client_id,
            client_secret=settings.auth_service_client_secret,
        )
    except ServiceTokenAcquisitionError:
        return "fail"
    return "ok"


def _decode_claims(authorization: str | None) -> Any:
    """Decode Authorization header into normalized claims."""
    try:
        return decode_bearer_token(authorization, _platform_auth_settings())
    except TokenMissingError as exc:
        raise AuthRequiredError() from exc
    except TokenInvalidError as exc:
        detail = str(exc).strip() or "Invalid or expired token"
        raise AuthInvalidError(detail) from exc


async def issue_service_token(*, audience: str | None = None) -> str:
    """Return an outbound service token for dependency calls."""
    auth_settings = _platform_auth_settings(audience=_service_token_audience(audience))
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
    """Validate a bearer token requiring ADMIN, MANAGER or SUPER_ADMIN role."""
    from fleet_service.errors import InsufficientRoleError

    claims = _decode_claims(authorization)
    role = claims.role
    if role not in {PlatformRole.SUPER_ADMIN, PlatformRole.MANAGER}:
        raise InsufficientRoleError("SUPER_ADMIN")
    actor_id = claims.sub.strip()
    if not actor_id:
        raise AuthInvalidError("Token is missing sub.")
    return AuthContext(actor_id=actor_id, role=role)


def require_super_admin_token(authorization: str | None) -> AuthContext:
    """Validate a bearer token requiring SUPER_ADMIN role (hard-delete only)."""
    from fleet_service.errors import InsufficientRoleError

    claims = _decode_claims(authorization)
    role = claims.role
    if role != PlatformRole.SUPER_ADMIN:
        raise InsufficientRoleError("SUPER_ADMIN")
    actor_id = claims.sub.strip()
    if not actor_id:
        raise AuthInvalidError("Token is missing sub.")
    return AuthContext(actor_id=actor_id, role=role)


def require_service_token(authorization: str | None, *, allowed_services: set[str] | None = None) -> AuthContext:
    """Validate a service bearer token for internal endpoints."""
    from fleet_service.errors import UnauthorizedInternalCallError

    claims = _decode_claims(authorization)
    role = claims.role
    actor_id = claims.sub.strip()
    service_name = (claims.service or "").strip()
    if role != PlatformRole.SERVICE or not actor_id or not service_name:
        raise UnauthorizedInternalCallError()
    if actor_id != service_name:
        raise UnauthorizedInternalCallError()
    if allowed_services is not None and service_name not in allowed_services:
        raise UnauthorizedInternalCallError()
    return AuthContext(actor_id=actor_id, role=PlatformRole.SERVICE, service_name=service_name)


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
