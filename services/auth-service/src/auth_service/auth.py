"""Auth dependencies for auth-service."""

from __future__ import annotations

from typing import Callable

from fastapi import Depends, Header
from platform_auth import PlatformRole
from platform_auth.dependencies import parse_bearer_token
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.database import get_session
from auth_service.errors import (
    auth_conflict,
    auth_forbidden,
    auth_unauthorized,
)
from auth_service.models import AuthCredentials
from auth_service.token_service import (
    InvalidUserRoleAssignmentsError,
    build_user_profile,
    decode_access_token,
)


async def current_user(
    authorization: str | None = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Resolve the current authenticated user."""
    if authorization is None:
        raise auth_unauthorized("Authorization header is required.")
    try:
        token = parse_bearer_token(authorization)
        claims = await decode_access_token(session, token)
    except Exception as exc:  # noqa: BLE001
        raise auth_unauthorized("Invalid or expired token.") from exc

    user = await session.get(AuthCredentials, claims.sub)
    if user is None or not user.is_active:
        raise auth_unauthorized("User is inactive or missing.")
    try:
        return await build_user_profile(session, user)
    except InvalidUserRoleAssignmentsError as exc:
        raise auth_conflict(str(exc)) from exc


def require_role(role_name: str) -> Callable:
    """Dependency factory to require a specific role."""
    # Validate at definition time that role_name is a known PlatformRole
    expected_role = str(PlatformRole(role_name))

    async def _require_role(
        user: dict[str, object] = Depends(current_user),
    ) -> dict[str, object]:
        if user.get("role") != expected_role:
            raise auth_forbidden(f"{expected_role} role required.")
        return user

    return _require_role
