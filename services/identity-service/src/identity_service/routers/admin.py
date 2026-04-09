"""Administrative endpoints for user and audit management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.auth import require_role
from identity_service.database import get_session
from identity_service.errors import identity_conflict, identity_not_found
from identity_service.models import (
    IdentityAuditLogModel,
    IdentityRefreshTokenModel,
    IdentityUserModel,
)
from identity_service.password import hash_secret
from identity_service.schemas import (
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    AuditListResponse,
    AuditLogResponse,
    UserListResponse,
    UserResponse,
)
from identity_service.token_service import (
    _write_outbox,
    assign_groups,
    build_user_profile,
    new_ulid,
    now_utc,
    serialize_user,
    write_audit,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _req_id(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


@router.get("/v1/users", response_model=UserListResponse)
async def list_users(
    username: str | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_role("SUPER_ADMIN")),
) -> UserListResponse:
    """List and filter users with cursor-based pagination."""
    query = (
        select(IdentityUserModel)
        .order_by(IdentityUserModel.user_id.asc())
        .limit(limit + 1)
    )
    if cursor:
        query = query.where(IdentityUserModel.user_id > cursor)
    if username:
        safe_username = username.replace("%", "\\%").replace("_", "\\_")
        query = query.where(IdentityUserModel.username.ilike(f"%{safe_username}%"))

    result = await session.execute(query)
    users = result.scalars().all()

    has_more = len(users) > limit
    page = list(users[:limit])
    next_cursor = page[-1].user_id if has_more else None

    items = []
    for user in page:
        profile = await build_user_profile(session, user)
        items.append(UserResponse(**profile))

    return UserListResponse(items=items, next_cursor=next_cursor)


@router.post("/v1/users", response_model=UserResponse, status_code=201)
async def create_user(
    request: Request,
    body: AdminCreateUserRequest,
    session: AsyncSession = Depends(get_session),
    admin=Depends(require_role("SUPER_ADMIN")),
) -> UserResponse:
    """Create a new user with group assignments."""
    existing = await session.execute(
        select(IdentityUserModel).where(IdentityUserModel.username == body.username)
    )
    if existing.scalar_one_or_none():
        raise identity_conflict("Username already exists.")

    existing_email = await session.execute(
        select(IdentityUserModel).where(IdentityUserModel.email == body.email)
    )
    if existing_email.scalar_one_or_none():
        raise identity_conflict("Email already exists.")

    user = IdentityUserModel(
        user_id=new_ulid(),
        username=body.username,
        email=body.email,
        password_hash=hash_secret(body.password),
        is_active=body.is_active,
        created_at_utc=now_utc(),
        updated_at_utc=now_utc(),
    )
    session.add(user)
    await session.flush()

    if body.groups:
        await assign_groups(session, user, [str(g) for g in body.groups])

    await write_audit(
        session,
        "USER",
        user.user_id,
        "CREATE",
        admin["user_id"],
        admin["role"],
        new_snapshot=serialize_user(
            user, mask_pii=True, groups=[str(g) for g in body.groups]
        ),
        request_id=_req_id(request),
    )
    await _write_outbox(
        session,
        "identity.user.created.v1",
        {
            "user_id": user.user_id,
            "username": user.username,
            "groups": [str(g) for g in body.groups],
            "occurred_at_utc": now_utc().isoformat(),
        },
        aggregate_id=user.user_id,
    )

    await session.commit()
    profile = await build_user_profile(session, user)
    return UserResponse(**profile)


@router.patch("/v1/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    request: Request,
    body: AdminUpdateUserRequest,
    session: AsyncSession = Depends(get_session),
    admin=Depends(require_role("SUPER_ADMIN")),
) -> UserResponse:
    """Update user attributes and group memberships."""
    user = await session.get(IdentityUserModel, user_id)
    if not user:
        raise identity_not_found("User not found.")

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
        if body.is_active is False and user.is_active:
            # Deactivation: stamp timestamp and revoke all active refresh tokens
            user.deactivated_at_utc = now_utc()
            await session.execute(
                update(IdentityRefreshTokenModel)
                .where(
                    IdentityRefreshTokenModel.user_id == user.user_id,
                    IdentityRefreshTokenModel.revoked_at_utc.is_(None),
                )
                .values(revoked_at_utc=now_utc())
            )
        user.is_active = body.is_active

    user.updated_at_utc = now_utc()

    if body.groups is not None:
        await assign_groups(session, user, [str(g) for g in body.groups])

    new_profile = await build_user_profile(session, user)
    new_snapshot = serialize_user(
        user,
        mask_pii=True,
        groups=new_profile["groups"],
        permissions=new_profile["permissions"],
    )

    await write_audit(
        session,
        "USER",
        user.user_id,
        "UPDATE",
        admin["user_id"],
        admin["role"],
        old_snapshot=old_snapshot,
        new_snapshot=new_snapshot,
        request_id=_req_id(request),
    )
    await _write_outbox(
        session,
        "identity.user.updated.v1",
        {
            "user_id": user.user_id,
            "occurred_at_utc": now_utc().isoformat(),
        },
        aggregate_id=user.user_id,
    )

    await session.commit()
    return UserResponse(**new_profile)


@router.get("/v1/audit", response_model=AuditListResponse)
async def list_audit_logs(
    target_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_role("SUPER_ADMIN")),
) -> AuditListResponse:
    """Retrieve audit logs with optional filtering and cursor-based pagination."""
    query = (
        select(IdentityAuditLogModel)
        .order_by(IdentityAuditLogModel.audit_id.desc())
        .limit(limit + 1)
    )
    if target_id:
        query = query.where(IdentityAuditLogModel.target_id == target_id)
    if cursor:
        query = query.where(IdentityAuditLogModel.audit_id < cursor)

    result = await session.execute(query)
    logs = result.scalars().all()

    has_more = len(logs) > limit
    page = list(logs[:limit])
    next_cursor = page[-1].audit_id if has_more else None

    items = [
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
        for log in page
    ]

    return AuditListResponse(items=items, next_cursor=next_cursor)
