"""Core utilities for Identity Service."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from identity_service.models import (
    IdentityAuditLogModel,
    IdentityGroupModel,
    IdentityGroupPermissionModel,
    IdentityOutboxModel,
    IdentityUserGroupModel,
    IdentityUserModel,
)

logger = logging.getLogger("identity_service.utils")

class RobustEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)

def now_utc() -> datetime:
    return datetime.now(UTC)

def new_ulid() -> str:
    return str(ULID())

async def write_audit(
    session: AsyncSession,
    target_type: str,
    target_id: str,
    action_type: str,
    actor_id: str,
    actor_role: str,
    old_snapshot: dict | str | None = None,
    new_snapshot: dict | str | None = None,
    request_id: str | None = None,
) -> None:
    audit = IdentityAuditLogModel(
        audit_id=new_ulid(),
        target_type=target_type,
        target_id=target_id,
        action_type=action_type,
        actor_id=actor_id,
        actor_role=actor_role,
        old_snapshot_json=json.dumps(old_snapshot, cls=RobustEncoder) if isinstance(old_snapshot, dict) else old_snapshot,
        new_snapshot_json=json.dumps(new_snapshot, cls=RobustEncoder) if isinstance(new_snapshot, dict) else new_snapshot,
        request_id=request_id,
        created_at_utc=now_utc(),
    )
    session.add(audit)

async def _write_outbox(
    session: AsyncSession,
    event_name: str,
    payload: dict,
    aggregate_id: str,
    aggregate_type: str = "USER",
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    outbox = IdentityOutboxModel(
        outbox_id=new_ulid(),
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=1,
        event_name=event_name,
        event_version=1,
        payload_json=json.dumps(payload, cls=RobustEncoder),
        publish_status="PENDING",
        created_at_utc=now_utc(),
        next_attempt_at_utc=now_utc(),
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    session.add(outbox)

def serialize_user(user: IdentityUserModel, mask_pii: bool = False, **kwargs) -> dict:
    data = {
        "user_id": user.user_id,
        "username": user.username,
        "email": "***" if mask_pii else user.email,
        "is_active": user.is_active,
        "created_at_utc": user.created_at_utc.isoformat(),
    }
    data.update(kwargs)
    return data

async def build_user_profile(session: AsyncSession, user: IdentityUserModel) -> dict:
    # Get direct groups
    group_query = select(IdentityGroupModel.group_name).join(
        IdentityUserGroupModel, IdentityUserGroupModel.group_id == IdentityGroupModel.group_id
    ).where(IdentityUserGroupModel.user_id == user.user_id)
    groups = (await session.execute(group_query)).scalars().all()

    # Get permissions
    perm_query = select(IdentityGroupPermissionModel.permission_key).join(
        IdentityUserGroupModel, IdentityUserGroupModel.group_id == IdentityGroupPermissionModel.group_id
    ).where(IdentityUserGroupModel.user_id == user.user_id)
    permissions = (await session.execute(perm_query)).scalars().all()

    return {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
        "groups": list(groups),
        "permissions": list(set(permissions)),
        "created_at_utc": user.created_at_utc,
        "updated_at_utc": user.updated_at_utc,
    }

async def assign_groups(session: AsyncSession, user: IdentityUserModel, group_names: list[str]) -> None:
    # Remove existing
    from sqlalchemy import delete
    await session.execute(
        delete(IdentityUserGroupModel).where(IdentityUserGroupModel.user_id == user.user_id)
    )
    
    # Resolve names to IDs
    res = await session.execute(
        select(IdentityGroupModel).where(IdentityGroupModel.group_name.in_(group_names))
    )
    found_groups = res.scalars().all()
    
    for g in found_groups:
        session.add(IdentityUserGroupModel(
            user_id=user.user_id,
            group_id=g.group_id,
            assigned_at=now_utc()
        ))
