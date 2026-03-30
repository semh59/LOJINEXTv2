"""Lifecycle API router for Driver Service (spec §3.5–3.8).

Endpoints:
  POST  /api/v1/drivers/{id}/inactivate   — deactivate a driver
  POST  /api/v1/drivers/{id}/reactivate   — reactivate a driver
  POST  /api/v1/drivers/{id}/soft-delete  — soft-delete a driver
  GET   /api/v1/drivers/{id}/audit        — fetch audit trail
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from driver_service.auth import AuthContext, admin_auth_dependency
from driver_service.database import get_session
from driver_service.enums import AuditActionType
from driver_service.errors import (
    driver_already_soft_deleted,
    driver_company_code_already_exists,
    driver_if_match_required,
    driver_internal_error,
    driver_not_found,
    driver_phone_already_exists,
    driver_telegram_already_exists,
    driver_validation_error,
    driver_version_mismatch,
)
from driver_service.models import DriverAuditLogModel, DriverModel, DriverOutboxModel
from driver_service.normalization import etag_from_row_version, parse_if_match
from driver_service.serializers import serialize_driver_admin, serialize_driver_for_role

logger = logging.getLogger("driver_service")
router = APIRouter(prefix="/api/v1/drivers", tags=["driver-lifecycle"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _new_ulid() -> str:
    return str(ULID())


async def _write_audit(
    session: AsyncSession,
    driver_id: str,
    action_type: str,
    actor_id: str,
    actor_role: str,
    *,
    changed_fields: dict | None = None,
    old_snapshot: dict | None = None,
    new_snapshot: dict | None = None,
    reason: str | None = None,
    request_id: str | None = None,
) -> None:
    audit = DriverAuditLogModel(
        audit_id=_new_ulid(),
        driver_id=driver_id,
        action_type=action_type,
        changed_fields_json=json.dumps(changed_fields) if changed_fields else None,
        old_snapshot_json=json.dumps(old_snapshot) if old_snapshot else None,
        new_snapshot_json=json.dumps(new_snapshot) if new_snapshot else None,
        actor_id=actor_id,
        actor_role=actor_role,
        reason=reason,
        request_id=request_id,
        created_at_utc=_now_utc(),
    )
    session.add(audit)


async def _write_outbox(session: AsyncSession, driver_id: str, event_name: str, payload: dict) -> None:
    outbox = DriverOutboxModel(
        outbox_id=_new_ulid(),
        driver_id=driver_id,
        event_name=event_name,
        event_version=1,
        payload_json=json.dumps(payload),
        publish_status="PENDING",
        retry_count=0,
        created_at_utc=_now_utc(),
        next_attempt_at_utc=_now_utc(),
    )
    session.add(outbox)


def _handle_integrity_error(exc: IntegrityError) -> None:
    detail = str(exc.orig) if exc.orig else str(exc)
    if "uq_driver_phone_e164_live" in detail:
        raise driver_phone_already_exists()
    if "uq_driver_telegram_user_id_live" in detail:
        raise driver_telegram_already_exists()
    if "uq_driver_company_code_live" in detail:
        raise driver_company_code_already_exists()
    raise driver_internal_error("Database constraint violation.")


async def _get_driver_with_etag_check(
    session: AsyncSession,
    driver_id: str,
    if_match: str | None,
) -> DriverModel:
    """Fetch driver and validate If-Match header."""
    expected_version = parse_if_match(if_match)
    if expected_version is None:
        raise driver_if_match_required()

    result = await session.execute(select(DriverModel).where(DriverModel.driver_id == driver_id))
    driver = result.scalar_one_or_none()
    if not driver:
        raise driver_not_found(driver_id)
    if driver.row_version != expected_version:
        raise driver_version_mismatch()
    return driver


# ---------------------------------------------------------------------------
# POST /api/v1/drivers/{driver_id}/inactivate
# ---------------------------------------------------------------------------


@router.post("/{driver_id}/inactivate")
async def inactivate_driver(
    driver_id: str,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(admin_auth_dependency),
    session: AsyncSession = Depends(get_session),
    if_match: str | None = Header(None, alias="If-Match"),
) -> dict:
    """Deactivate a driver (spec §3.5).

    State transitions: ACTIVE → INACTIVE (idempotent if already INACTIVE).
    SOFT_DELETED → INACTIVE is forbidden.
    BR-08: inactive_reason is required.
    """
    from driver_service.schemas import InactivateDriverRequest

    request_id = getattr(request.state, "request_id", None)
    now = _now_utc()

    driver = await _get_driver_with_etag_check(session, driver_id, if_match)

    if driver.soft_deleted_at_utc is not None:
        raise driver_already_soft_deleted()

    # Parse body
    body_bytes = await request.body()
    if not body_bytes:
        raise driver_validation_error("Request body is required.")

    body = InactivateDriverRequest.model_validate_json(body_bytes)

    # Idempotent if already INACTIVE
    if driver.status == "INACTIVE":
        response.headers["ETag"] = etag_from_row_version(driver.row_version)
        return serialize_driver_for_role(driver, auth.role)

    # Capture snapshots
    old_snapshot = serialize_driver_admin(driver)

    # Transition ACTIVE → INACTIVE
    old_status = driver.status
    driver.status = "INACTIVE"
    driver.inactive_reason = body.inactive_reason
    if body.employment_end_date:
        driver.employment_end_date = body.employment_end_date
    driver.row_version += 1
    driver.updated_at_utc = now
    driver.updated_by_actor_id = auth.actor_id

    new_snapshot = serialize_driver_admin(driver)

    await _write_audit(
        session,
        driver_id,
        AuditActionType.STATUS_CHANGE,
        auth.actor_id,
        auth.role,
        changed_fields={"status": [old_status, "INACTIVE"]},
        old_snapshot=old_snapshot,
        new_snapshot=new_snapshot,
        reason=body.inactive_reason,
        request_id=request_id,
    )
    await _write_outbox(
        session,
        driver_id,
        "driver.inactivated.v1",
        {
            "driver_id": driver_id,
            "reason": body.inactive_reason,
            "row_version": driver.row_version,
            "updated_at_utc": now.isoformat(),
        },
    )

    await session.commit()
    await session.refresh(driver)
    response.headers["ETag"] = etag_from_row_version(driver.row_version)
    return serialize_driver_for_role(driver, auth.role)


# ---------------------------------------------------------------------------
# POST /api/v1/drivers/{driver_id}/reactivate
# ---------------------------------------------------------------------------


@router.post("/{driver_id}/reactivate")
async def reactivate_driver(
    driver_id: str,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(admin_auth_dependency),
    session: AsyncSession = Depends(get_session),
    if_match: str | None = Header(None, alias="If-Match"),
) -> dict:
    """Reactivate a driver (spec §3.6).

    Transitions: INACTIVE → ACTIVE, SOFT_DELETED → ACTIVE (restore).
    On restore: clears soft_deleted_at_utc, soft_deleted_by_actor_id, soft_delete_reason.
    If ALREADY ACTIVE, idempotent return.
    Reactivation may conflict if phone/tel/code is now taken by another live driver.
    """
    request_id = getattr(request.state, "request_id", None)
    now = _now_utc()

    driver = await _get_driver_with_etag_check(session, driver_id, if_match)

    # Idempotent if already ACTIVE and not soft-deleted
    if driver.status == "ACTIVE" and driver.soft_deleted_at_utc is None:
        response.headers["ETag"] = etag_from_row_version(driver.row_version)
        return serialize_driver_for_role(driver, auth.role)

    # Capture status and snapshots
    old_status = driver.status
    was_soft_deleted = driver.soft_deleted_at_utc is not None
    old_snapshot = serialize_driver_admin(driver)

    # Perform reactivation
    driver.status = "ACTIVE"
    driver.inactive_reason = None

    # If restoring from soft delete, clear soft-delete fields
    if was_soft_deleted:
        driver.soft_deleted_at_utc = None
        driver.soft_deleted_by_actor_id = None
        driver.soft_delete_reason = None

    driver.row_version += 1
    driver.updated_at_utc = now
    driver.updated_by_actor_id = auth.actor_id

    new_snapshot = serialize_driver_admin(driver)

    action_type = AuditActionType.RESTORE if was_soft_deleted else AuditActionType.STATUS_CHANGE
    await _write_audit(
        session,
        driver_id,
        action_type,
        auth.actor_id,
        auth.role,
        changed_fields={"status": [old_status, "ACTIVE"], "restored_from_soft_delete": was_soft_deleted},
        old_snapshot=old_snapshot,
        new_snapshot=new_snapshot,
        request_id=request_id,
    )
    await _write_outbox(
        session,
        driver_id,
        "driver.reactivated.v1",
        {
            "driver_id": driver_id,
            "restored_from_soft_delete": was_soft_deleted,
            "row_version": driver.row_version,
            "updated_at_utc": now.isoformat(),
        },
    )

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        _handle_integrity_error(exc)

    await session.refresh(driver)
    response.headers["ETag"] = etag_from_row_version(driver.row_version)
    return serialize_driver_for_role(driver, auth.role)


# ---------------------------------------------------------------------------
# POST /api/v1/drivers/{driver_id}/soft-delete
# ---------------------------------------------------------------------------


@router.post("/{driver_id}/soft-delete")
async def soft_delete_driver(
    driver_id: str,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(admin_auth_dependency),
    session: AsyncSession = Depends(get_session),
    if_match: str | None = Header(None, alias="If-Match"),
) -> dict:
    """Soft-delete a driver (spec §3.7).

    Any status → SOFT_DELETED. Idempotent if already soft-deleted.
    Soft-deleted drivers remain queryable via GET detail with lifecycle_state=SOFT_DELETED.
    """
    from driver_service.schemas import SoftDeleteDriverRequest

    request_id = getattr(request.state, "request_id", None)
    now = _now_utc()

    driver = await _get_driver_with_etag_check(session, driver_id, if_match)

    # Idempotent
    if driver.soft_deleted_at_utc is not None:
        response.headers["ETag"] = etag_from_row_version(driver.row_version)
        return serialize_driver_for_role(driver, auth.role)

    # Parse body
    body_bytes = await request.body()
    if not body_bytes:
        raise driver_validation_error("Request body with reason is required.")
    body = SoftDeleteDriverRequest.model_validate_json(body_bytes)

    # Capture snapshots
    old_snapshot = serialize_driver_admin(driver)

    driver.soft_deleted_at_utc = now
    driver.soft_deleted_by_actor_id = auth.actor_id
    driver.soft_delete_reason = body.reason
    driver.row_version += 1
    driver.updated_at_utc = now
    driver.updated_by_actor_id = auth.actor_id

    new_snapshot = serialize_driver_admin(driver)

    await _write_audit(
        session,
        driver_id,
        AuditActionType.SOFT_DELETE,
        auth.actor_id,
        auth.role,
        old_snapshot=old_snapshot,
        new_snapshot=new_snapshot,
        reason=body.reason,
        request_id=request_id,
    )
    await _write_outbox(
        session,
        driver_id,
        "driver.soft_deleted.v1",
        {
            "driver_id": driver_id,
            "reason": body.reason,
            "row_version": driver.row_version,
            "soft_deleted_at_utc": now.isoformat(),
        },
    )

    await session.commit()
    await session.refresh(driver)
    response.headers["ETag"] = etag_from_row_version(driver.row_version)
    return serialize_driver_for_role(driver, auth.role)


# ---------------------------------------------------------------------------
# GET /api/v1/drivers/{driver_id}/audit — audit trail
# ---------------------------------------------------------------------------


@router.get("/{driver_id}/audit")
async def get_audit_trail(
    driver_id: str,
    auth: AuthContext = Depends(admin_auth_dependency),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> dict:
    """Fetch paginated audit trail for a driver (spec §3.8)."""
    # Verify driver exists (even if soft-deleted)
    result = await session.execute(select(DriverModel.driver_id).where(DriverModel.driver_id == driver_id))
    if not result.scalar_one_or_none():
        raise driver_not_found(driver_id)

    # Count
    count_query = select(func.count()).where(DriverAuditLogModel.driver_id == driver_id)
    total = (await session.execute(count_query)).scalar() or 0

    # Fetch
    offset = (page - 1) * per_page
    query = (
        select(DriverAuditLogModel)
        .where(DriverAuditLogModel.driver_id == driver_id)
        .order_by(DriverAuditLogModel.created_at_utc.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await session.execute(query)
    entries = result.scalars().all()

    items = [
        {
            "audit_id": e.audit_id,
            "driver_id": e.driver_id,
            "action_type": e.action_type,
            "changed_fields_json": e.changed_fields_json,
            "actor_id": e.actor_id,
            "actor_role": e.actor_role,
            "reason": e.reason,
            "request_id": e.request_id,
            "created_at_utc": e.created_at_utc.isoformat() if e.created_at_utc else None,
        }
        for e in entries
    ]

    return {"page": page, "per_page": per_page, "total": total, "items": items}
