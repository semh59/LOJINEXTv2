"""Administrative endpoints for user and audit management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.auth import require_role
from identity_service.database import get_session
from identity_service.models import IdentityAuditLogModel, IdentityUserModel
from identity_service.password import hash_secret
from identity_service.schemas import (
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    AuditLogResponse,
    UserResponse,
)
from identity_service.token_service import (
    _now_utc,
    _new_ulid,
    _write_audit,
    assign_groups,
    build_user_profile,
    serialize_user,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/v1/users", response_model=list[UserResponse])
async def list_users(
    username: str | None = None,
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_role("SUPER_ADMIN")),
) -> list[UserResponse]:
    """List and filter users."""
    query = select(IdentityUserModel)
    if username:
        safe_username = username.replace("%", "\\%").replace("_", "\\_")
        query = query.where(IdentityUserModel.username.ilike(f"%{safe_username}%"))

    result = await session.execute(query)
    users = result.scalars().all()

    response = []
    for user in users:
        profile = await build_user_profile(session, user)
        response.append(UserResponse(**profile))
    return response


@router.post("/v1/users", response_model=UserResponse, status_code=201)
async def create_user(
    body: AdminCreateUserRequest,
    session: AsyncSession = Depends(get_session),
    admin=Depends(require_role("SUPER_ADMIN")),
) -> UserResponse:
    """Create a new user with group assignments."""
    # Check if username exists
    existing = await session.execute(
        select(IdentityUserModel).where(IdentityUserModel.username == body.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists.")

    # Check if email exists
    existing_email = await session.execute(
        select(IdentityUserModel).where(IdentityUserModel.email == body.email)
    )
    if existing_email.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already exists.")

    user = IdentityUserModel(
        user_id=_new_ulid(),
        username=body.username,
        email=body.email,
        password_hash=hash_secret(body.password),
        is_active=body.is_active,
        created_at_utc=_now_utc(),
        updated_at_utc=_now_utc(),
    )
    session.add(user)
    await session.flush()

    if body.groups:
        await assign_groups(session, user, [str(g) for g in body.groups])

    await _write_audit(
        session,
        "USER",
        user.user_id,
        "CREATE",
        admin["user_id"],
        admin["role"],
        new_snapshot=serialize_user(
            user, mask_pii=True, groups=[str(g) for g in body.groups]
        ),
    )

    await session.commit()
    profile = await build_user_profile(session, user)
    return UserResponse(**profile)


@router.patch("/v1/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: AdminUpdateUserRequest,
    session: AsyncSession = Depends(get_session),
    admin=Depends(require_role("SUPER_ADMIN")),
) -> UserResponse:
    """Update user attributes and group memberships."""
    user = await session.get(IdentityUserModel, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    old_profile = await build_user_profile(session, user)
    old_snapshot = serialize_user(
        user,
        mask_pii=True,
        groups=old_profile["groups"],
        permissions=old_profile["permissions"],
    )

    if body.email:
        user.email = body.email
    if body.password:
        user.password_hash = hash_secret(body.password)
    if body.is_active is not None:
        user.is_active = body.is_active

    user.updated_at_utc = _now_utc()

    if body.groups is not None:
        await assign_groups(session, user, [str(g) for g in body.groups])

    new_profile = await build_user_profile(session, user)
    new_snapshot = serialize_user(
        user,
        mask_pii=True,
        groups=new_profile["groups"],
        permissions=new_profile["permissions"],
    )

    await _write_audit(
        session,
        "USER",
        user.user_id,
        "UPDATE",
        admin["user_id"],
        admin["role"],
        old_snapshot=old_snapshot,
        new_snapshot=new_snapshot,
    )

    await session.commit()
    return UserResponse(**new_profile)


@router.get("/v1/audit", response_model=list[AuditLogResponse])
async def list_audit_logs(
    target_id: str | None = None,
    limit: int = Query(100, le=1000),
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_role("SUPER_ADMIN")),
) -> list[AuditLogResponse]:
    """Retrieve audit logs with optional filtering."""
    query = (
        select(IdentityAuditLogModel)
        .order_by(IdentityAuditLogModel.created_at_utc.desc())
        .limit(limit)
    )
    if target_id:
        query = query.where(IdentityAuditLogModel.target_id == target_id)

    result = await session.execute(query)
    logs = result.scalars().all()

    return [
        AuditLogResponse(
            audit_id=log.audit_id,
            target_type=log.target_type,
            target_id=log.target_id,
            action_type=log.action_type,
            actor_id=log.actor_id,
            actor_role=log.actor_role,
            old_snapshot=log.old_snapshot_json,
            new_snapshot=log.new_snapshot_json,
            created_at_utc=log.created_at_utc,
        )
        for log in logs
    ]
