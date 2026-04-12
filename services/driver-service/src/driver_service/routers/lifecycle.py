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
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from driver_service.auth import AuthContext, admin_auth_dependency
from driver_service.database import get_session
from driver_service.enums import AuditActionType, DriverStatus
from driver_service.errors import (
    driver_company_code_already_exists,
    driver_if_match_required,
    driver_internal_error,
    driver_not_found,
    driver_phone_already_exists,
    driver_telegram_already_exists,
    driver_validation_error,
    driver_version_mismatch,
)
from driver_service.idempotency import (
    check_idempotency,
    compute_endpoint_fingerprint,
    save_idempotency_record,
)
from driver_service.models import DriverAuditLogModel, DriverModel, DriverOutboxModel
from driver_service.normalization import etag_from_row_version, mask_phone_for_manager, parse_if_match
from driver_service.serializers import serialize_driver_admin, serialize_driver_for_role
from driver_service.state_machine import DriverStateMachine

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
    changed_fields: dict[str, Any] | None = None,
    old_snapshot: dict[str, Any] | None = None,
    new_snapshot: dict[str, Any] | None = None,
    reason: str | None = None,
    request_id: str | None = None,
) -> None:
    # PII Hardening: Mask sensitive fields in snapshots
    if old_snapshot and "phone" in old_snapshot:
        old_snapshot["phone"] = mask_phone_for_manager(old_snapshot["phone"])
    if new_snapshot and "phone" in new_snapshot:
        new_snapshot["phone"] = mask_phone_for_manager(new_snapshot["phone"])

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


async def _write_outbox(
    session: AsyncSession,
    driver_id: str,
    event_name: str,
    payload: dict[str, Any],
    *,
    request_id: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    outbox = DriverOutboxModel(
        outbox_id=_new_ulid(),
        aggregate_type="DRIVER",
        aggregate_id=driver_id,
        aggregate_version=1,
        driver_id=driver_id,
        event_name=event_name,
        event_version=1,
        payload_json=json.dumps(payload),
        partition_key=driver_id,
        publish_status="PENDING",
        attempt_count=0,
        request_id=request_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
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
    if "driver_outbox_driver_id_fkey" in detail and "RESTRICT" in detail:
        raise driver_validation_error("Cannot hard-delete driver with pending outbox events.")
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
) -> dict[str, Any]:
    """Deactivate a driver (spec §3.5).
    State transitions: ACTIVE → INACTIVE.
    """
    from driver_service.schemas import InactivateDriverRequest

    request_id = getattr(request.state, "request_id", None)
    now = _now_utc()

    # Idempotency Check
    fingerprint = compute_endpoint_fingerprint("POST", f"/api/v1/drivers/{driver_id}/inactivate")
    if request_id:
        existing = await check_idempotency(session, request_id, fingerprint)
        if existing:
            response.status_code = 200
            return json.loads(existing.response_body_json) if existing.response_body_json else {}

    driver = await _get_driver_with_etag_check(session, driver_id, if_match)

    # Parse body
    body_bytes = await request.body()
    if not body_bytes:
        raise driver_validation_error("Request body is required.")
    body = InactivateDriverRequest.model_validate_json(body_bytes)

    # Idempotent if already INACTIVE
    if driver.status == DriverStatus.INACTIVE:
        response.headers["ETag"] = etag_from_row_version(driver.row_version)
        return serialize_driver_for_role(driver, auth.role)

    # Capture snapshots
    old_snapshot = serialize_driver_admin(driver)
    old_status = driver.status

    # Transition to INACTIVE
    sm = DriverStateMachine(driver.status)
    sm.transition_to(DriverStatus.INACTIVE)

    driver.status = DriverStatus.INACTIVE
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
        changed_fields={"status": [old_status, DriverStatus.INACTIVE]},
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
        request_id=request_id,
        correlation_id=request_id,
    )

    # Save Idempotency
    result_body = serialize_driver_for_role(driver, auth.role)
    if request_id:
        await save_idempotency_record(
            session,
            request_id,
            fingerprint,
            200,
            result_body,
            auth.actor_id,
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
) -> dict[str, Any]:
    """Reactivate a driver (spec §3.6).
    Transitions: INACTIVE → ACTIVE, SUSPENDED → ACTIVE.
    """
    request_id = getattr(request.state, "request_id", None)
    now = _now_utc()

    # Idempotency Check
    fingerprint = compute_endpoint_fingerprint("POST", f"/api/v1/drivers/{driver_id}/reactivate")
    if request_id:
        existing = await check_idempotency(session, request_id, fingerprint)
        if existing:
            response.status_code = 200
            return json.loads(existing.response_body_json) if existing.response_body_json else {}

    driver = await _get_driver_with_etag_check(session, driver_id, if_match)

    # Idempotent if already ACTIVE
    if driver.status == DriverStatus.ACTIVE:
        response.headers["ETag"] = etag_from_row_version(driver.row_version)
        return serialize_driver_for_role(driver, auth.role)

    # Capture status and snapshots
    old_status = driver.status
    old_snapshot = serialize_driver_admin(driver)

    # Transition to ACTIVE
    sm = DriverStateMachine(driver.status)
    sm.transition_to(DriverStatus.ACTIVE)

    driver.status = DriverStatus.ACTIVE
    driver.inactive_reason = None
    driver.soft_deleted_at_utc = None
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
        changed_fields={"status": [old_status, DriverStatus.ACTIVE]},
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
            "row_version": driver.row_version,
            "updated_at_utc": now.isoformat(),
        },
        request_id=request_id,
        correlation_id=request_id,
    )

    # Save Idempotency
    result_body = serialize_driver_for_role(driver, auth.role)
    if request_id:
        await save_idempotency_record(
            session,
            request_id,
            fingerprint,
            200,
            result_body,
            auth.actor_id,
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
) -> dict[str, Any]:
    """Cancel/Decommission a driver (spec §3.7).
    Any status → CANCELLED.
    """
    from driver_service.schemas import SoftDeleteDriverRequest

    request_id = getattr(request.state, "request_id", None)
    now = _now_utc()

    # Idempotency Check
    fingerprint = compute_endpoint_fingerprint("POST", f"/api/v1/drivers/{driver_id}/soft-delete")
    if request_id:
        existing = await check_idempotency(session, request_id, fingerprint)
        if existing:
            response.status_code = 200
            return json.loads(existing.response_body_json) if existing.response_body_json else {}

    driver = await _get_driver_with_etag_check(session, driver_id, if_match)

    # Idempotent
    if driver.status == DriverStatus.CANCELLED:
        response.headers["ETag"] = etag_from_row_version(driver.row_version)
        return serialize_driver_for_role(driver, auth.role)

    # Parse body
    body_bytes = await request.body()
    if not body_bytes:
        raise driver_validation_error("Request body with reason is required.")
    body = SoftDeleteDriverRequest.model_validate_json(body_bytes)

    # Capture snapshots
    old_snapshot = serialize_driver_admin(driver)
    old_status = driver.status

    # Transition to CANCELLED
    sm = DriverStateMachine(driver.status)
    sm.transition_to(DriverStatus.CANCELLED)

    driver.status = DriverStatus.CANCELLED
    driver.inactive_reason = body.reason
    driver.soft_deleted_at_utc = now
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
        changed_fields={"status": [old_status, DriverStatus.CANCELLED]},
        old_snapshot=old_snapshot,
        new_snapshot=new_snapshot,
        reason=body.reason,
        request_id=request_id,
    )
    await _write_outbox(
        session,
        driver_id,
        "driver.cancelled.v1",
        {
            "driver_id": driver_id,
            "reason": body.reason,
            "row_version": driver.row_version,
            "cancelled_at_utc": now.isoformat(),
        },
        request_id=request_id,
        correlation_id=request_id,
    )

    # Save Idempotency
    result_body = serialize_driver_for_role(driver, auth.role)
    if request_id:
        await save_idempotency_record(
            session,
            request_id,
            fingerprint,
            200,
            result_body,
            auth.actor_id,
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
# GET /api/v1/drivers/{driver_id}/audit — audit trail
# ---------------------------------------------------------------------------


@router.get("/{driver_id}/audit")
async def get_audit_trail(
    driver_id: str,
    auth: AuthContext = Depends(admin_auth_dependency),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Fetch paginated audit trail for a driver (spec §3.8)."""
    # BUG-2 Fix: Do not check DriverModel existence, as hard-deleted drivers should still have audit logs.
    # The audit logs are immutable and stored with the driver_id as a plain string.

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
