from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, cast

import anyio
from fastapi import Header
from platform_auth import (
    AuthContext,
    AuthSettings,
    PlatformRole,
    ServiceTokenAcquisitionError,
    ServiceTokenCache,
    TokenClaims,
    TokenMissingError,
    async_decode_bearer_token,
)
from platform_auth.key_provider import build_verification_provider

from trip_service.config import settings
from trip_service.errors import (
    trip_auth_invalid,
    trip_auth_required,
    trip_forbidden,
)

_SERVICE_TOKEN_CACHE = ServiceTokenCache()
_DEFAULT_SERVICE_AUDIENCE = "lojinext-platform"


def _platform_auth_settings(*, audience: str | None = None) -> AuthSettings:
    """Build shared auth settings for inbound or outbound token handling."""
    if audience:
        effective_audience: str | tuple[str, ...] | None = audience
    elif settings.auth_audience:
        effective_audience = (settings.auth_audience, settings.service_name)
    else:
        effective_audience = None

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


def _fetch_jwks_payload_sync(jwks_url: str) -> dict[str, Any] | None:
    """Synchronously fetch JWKS payload (to be called in worker thread)."""
    request = urllib.request.Request(jwks_url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


async def _probe_jwks_document(jwks_url: str) -> bool:
    """Return whether the configured JWKS endpoint serves a usable keys array."""
    payload = await anyio.to_thread.run_sync(_fetch_jwks_payload_sync, jwks_url)
    return isinstance(payload, dict) and isinstance(payload.get("keys"), list) and bool(payload["keys"])


async def auth_verify_status() -> str:
    """Return `ok` when inbound auth settings are live and coherent."""
    auth_settings = _platform_auth_settings()
    if auth_settings.algorithm.upper() != "RS256":
        return "fail"
    if not auth_settings.issuer or not auth_settings.audience or not auth_settings.jwks_url:
        return "fail"
    if not await _probe_jwks_document(auth_settings.jwks_url):
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


async def _decode_claims(authorization: str | None) -> TokenClaims:
    """Decode an Authorization header into normalized claims."""
    try:
        return await async_decode_bearer_token(authorization, _platform_auth_settings())
    except TokenMissingError as exc:
        raise trip_auth_required() from exc
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or "Token invalid"
        raise trip_auth_invalid(detail) from exc


async def issue_internal_service_token(*, audience: str | None = None) -> str:
    """Return an outbound service token for dependency calls."""
    auth_settings = _platform_auth_settings(audience=_service_token_audience(audience))
    try:
        return cast(
            str,
            await _SERVICE_TOKEN_CACHE.get_token(
                service_name=settings.service_name,
                audience=auth_settings.audience if isinstance(auth_settings.audience, str) else None,
                token_url=settings.auth_service_token_url,
                client_id=settings.auth_service_client_id,
                client_secret=settings.auth_service_client_secret,
            ),
        )
    except ServiceTokenAcquisitionError as exc:
        raise RuntimeError(str(exc)) from exc


async def require_user_token(
    authorization: str | None,
) -> AuthContext:
    """Validate a user bearer token and return the caller context."""
    if authorization is None:
        raise trip_auth_required()

    claims = await _decode_claims(authorization)
    role = str(claims.role)

    # §5.1 Alignment: Use PlatformRole directly instead of local ActorType aliases
    authorized_roles = {PlatformRole.MANAGER.value, PlatformRole.OPERATOR.value, PlatformRole.SUPER_ADMIN.value}
    if role not in authorized_roles:
        raise trip_forbidden(f"User token does not have an authorized role: {role}")

    actor_id = claims.sub.strip()
    if not actor_id:
        raise trip_auth_invalid("Token is missing sub.")
    return AuthContext(actor_id=actor_id, role=role)


async def require_service_token(authorization: str | None, allowed_services: set[str]) -> AuthContext:
    """Validate a service bearer token and enforce the allowed service names."""
    claims = await _decode_claims(authorization)
    role = str(claims.role)
    service_name = (claims.service or "").strip()
    actor_id = claims.sub.strip()
    if role != PlatformRole.SERVICE.value or not service_name or not actor_id:
        raise trip_forbidden("Token is not a valid service token.")
    if service_name not in allowed_services:
        raise trip_forbidden("Service token is not allowed for this endpoint.")
    return AuthContext(actor_id=actor_id, role=role, service_name=service_name)


async def user_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for public user-authenticated endpoints."""
    return await require_user_token(authorization)


async def telegram_service_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for Telegram-owned internal endpoints."""
    return await require_service_token(authorization, {"telegram-service"})


async def excel_service_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for Excel-owned internal endpoints."""
    return await require_service_token(authorization, {"excel-service"})


async def reference_service_auth_dependency(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AuthContext:
    """FastAPI dependency for service-only trip reference checks."""
    return await require_service_token(authorization, {"driver-service", "fleet-service"})
