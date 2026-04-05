"""Principal helpers derived from normalized claims."""

from __future__ import annotations

from dataclasses import dataclass

from platform_auth.claims import TokenClaims
from platform_auth.errors import TokenForbiddenError
from platform_auth.roles import PlatformRole


@dataclass(frozen=True)
class UserPrincipal:
    """User caller principal."""

    subject: str
    role: str
    groups: tuple[str, ...]
    permissions: tuple[str, ...]


@dataclass(frozen=True)
class ServicePrincipal:
    """Service caller principal."""

    subject: str
    service_name: str
    role: str = PlatformRole.SERVICE


def principal_from_claims(claims: TokenClaims) -> UserPrincipal | ServicePrincipal:
    """Translate claims into a caller principal."""
    if claims.is_service:
        if not claims.service:
            raise TokenForbiddenError("Service token is missing service claim.")
        return ServicePrincipal(subject=claims.sub, service_name=claims.service)
    return UserPrincipal(
        subject=claims.sub,
        role=claims.role,
        groups=claims.groups,
        permissions=claims.permissions,
    )
