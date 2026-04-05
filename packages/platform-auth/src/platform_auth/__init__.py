"""Shared authentication primitives for LOJINEXT services."""

from platform_auth.claims import TokenClaims
from platform_auth.dependencies import decode_bearer_token, parse_bearer_token
from platform_auth.errors import (
    PlatformAuthError,
    TokenForbiddenError,
    TokenInvalidError,
    TokenMissingError,
)
from platform_auth.jwt_codec import issue_token, verify_token
from platform_auth.principals import ServicePrincipal, UserPrincipal, principal_from_claims
from platform_auth.roles import PlatformRole
from platform_auth.service_tokens import ServiceTokenAcquisitionError, ServiceTokenCache
from platform_auth.settings import AuthSettings
from platform_auth.token_factory import ServiceTokenFactory

__all__ = [
    "AuthSettings",
    "PlatformAuthError",
    "PlatformRole",
    "ServicePrincipal",
    "ServiceTokenAcquisitionError",
    "ServiceTokenCache",
    "ServiceTokenFactory",
    "TokenClaims",
    "TokenForbiddenError",
    "TokenInvalidError",
    "TokenMissingError",
    "UserPrincipal",
    "decode_bearer_token",
    "issue_token",
    "parse_bearer_token",
    "principal_from_claims",
    "verify_token",
]
