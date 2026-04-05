"""Admin endpoints for user management."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from identity_service.auth import require_super_admin
from identity_service.database import get_session
from identity_service.models import IdentityUserModel
from identity_service.password import hash_secret
from identity_service.schemas import AdminCreateUserRequest, AdminUpdateUserRequest, UserResponse
from identity_service.token_service import assign_groups, build_user_profile

router = APIRouter(prefix="/admin/v1/users", tags=["identity-admin"])


def _new_ulid() -> str:
    return str(ULID())


def _now_utc() -> datetime:
    return datetime.now(UTC)


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    body: AdminCreateUserRequest,
    session: AsyncSession = Depends(get_session),
    admin: dict[str, object] = Depends(require_super_admin),
) -> UserResponse:
    """Create a new managed user."""
    del admin
    existing = await session.execute(
        select(IdentityUserModel).where(
            or_(IdentityUserModel.username == body.username, IdentityUserModel.email == str(body.email))
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="User with same username or email already exists.")

    user = IdentityUserModel(
        user_id=_new_ulid(),
        username=body.username,
        email=str(body.email),
        password_hash=hash_secret(body.password),
        is_active=body.is_active,
        created_at_utc=_now_utc(),
        updated_at_utc=_now_utc(),
    )
    session.add(user)
    await session.flush()
    await assign_groups(session, user, body.groups)
    await session.commit()
    return UserResponse(**(await build_user_profile(session, user)))


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: AdminUpdateUserRequest,
    session: AsyncSession = Depends(get_session),
    admin: dict[str, object] = Depends(require_super_admin),
) -> UserResponse:
    """Update a managed user."""
    del admin
    user = await session.get(IdentityUserModel, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if body.email is not None:
        user.email = str(body.email)
    if body.password is not None:
        user.password_hash = hash_secret(body.password)
    if body.is_active is not None:
        user.is_active = body.is_active
    user.updated_at_utc = _now_utc()
    if body.groups is not None:
        await assign_groups(session, user, body.groups)
    await session.commit()
    return UserResponse(**(await build_user_profile(session, user)))
