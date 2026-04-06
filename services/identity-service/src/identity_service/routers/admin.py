"""Admin endpoints for user management."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from identity_service.auth import require_super_admin
from identity_service.database import get_session
from identity_service.models import IdentityUserModel
from identity_service.password import hash_secret
from identity_service.schemas import (
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    UserResponse,
)
from identity_service.token_service import (
    InvalidUserRoleAssignmentsError,
    _write_audit,
    _write_outbox,
    assign_groups,
    build_user_profile,
    serialize_user,
)

router = APIRouter(prefix="/admin/v1/users", tags=["identity-admin"])


def _new_ulid() -> str:
    return str(ULID())


def _now_utc() -> datetime:
    return datetime.now(UTC)


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    body: AdminCreateUserRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    admin: dict[str, object] = Depends(require_super_admin),
) -> UserResponse:
    """Create a new managed user."""
    existing = await session.execute(
        select(IdentityUserModel).where(
            or_(
                IdentityUserModel.username == body.username,
                IdentityUserModel.email == str(body.email),
            )
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409, detail="User with same username or email already exists."
        )

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

    admin_actor_id = str(admin.get("user_id", "SYSTEM"))
    admin_role = str(admin.get("role", "SUPER_ADMIN"))
    request_id = getattr(request.state, "request_id", None)

    await _write_audit(
        session,
        "USER",
        user.user_id,
        "CREATE",
        admin_actor_id,
        admin_role,
        new_snapshot=serialize_user(user, mask_pii=True),
        request_id=request_id,
    )
    await _write_outbox(
        session,
        "identity.user.created.v1",
        {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "occurred_at_utc": _now_utc().isoformat(),
        },
        aggregate_id=user.user_id,
    )

    await session.commit()
    try:
        return UserResponse(**(await build_user_profile(session, user)))
    except InvalidUserRoleAssignmentsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: AdminUpdateUserRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    admin: dict[str, object] = Depends(require_super_admin),
) -> UserResponse:
    """Update a managed user."""
    user = await session.get(IdentityUserModel, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    old_snapshot = serialize_user(user)

    if body.email is not None:
        user.email = str(body.email)
    if body.password is not None:
        user.password_hash = hash_secret(body.password)
    if body.is_active is not None:
        user.is_active = body.is_active
    user.updated_at_utc = _now_utc()
    if body.groups is not None:
        await assign_groups(session, user, body.groups)

    # Extract actor info from admin dependency
    admin_actor_id = str(admin.get("user_id", "SYSTEM"))
    admin_role = str(admin.get("role", "SUPER_ADMIN"))
    request_id = getattr(request.state, "request_id", None)

    await _write_audit(
        session,
        "USER",
        user.user_id,
        "UPDATE",
        admin_actor_id,
        admin_role,
        old_snapshot=old_snapshot,
        new_snapshot=serialize_user(user, mask_pii=True),
        request_id=request_id,
    )
    await _write_outbox(
        session,
        "identity.user.updated.v1",
        {
            "user_id": user.user_id,
            "username": user.username,
            "occurred_at_utc": _now_utc().isoformat(),
        },
        aggregate_id=user.user_id,
    )

    try:
        await session.commit()
    except Exception:
        await session.rollback()
        # Check if it's a uniqueness conflict (email)
        # Note: In a real production app, we'd use a more specific check for the constraint name,
        # but for this pass, mapping all IntegrityErrors on update to 409 is the target hardening.
        raise HTTPException(
            status_code=409, detail="User with same email already exists."
        )

    try:
        return UserResponse(**(await build_user_profile(session, user)))
    except InvalidUserRoleAssignmentsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
