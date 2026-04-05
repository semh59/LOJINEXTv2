"""Auth dependencies for identity-service."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from platform_auth.dependencies import parse_bearer_token
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.database import get_session
from identity_service.models import IdentityUserModel
from identity_service.token_service import build_user_profile, decode_access_token


async def current_user(
    authorization: str | None = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Resolve the current authenticated user."""
    if authorization is None:
        raise HTTPException(status_code=401, detail="Authorization header is required.")
    try:
        token = parse_bearer_token(authorization)
        claims = await decode_access_token(session, token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc

    user = await session.get(IdentityUserModel, claims.sub)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive or missing.")
    return await build_user_profile(session, user)


async def require_super_admin(
    user: dict[str, object] = Depends(current_user),
) -> dict[str, object]:
    """Require the caller to be a SUPER_ADMIN."""
    if user.get("role") != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="SUPER_ADMIN role required.")
    return user
