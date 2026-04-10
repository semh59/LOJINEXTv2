"""Maintenance API router for Driver Service (spec §3.14–3.15).

Feature-flagged endpoints:
  POST  /internal/v1/drivers/{id}/hard-delete  — permanent deletion
  POST  /internal/v1/drivers/merge             — merge duplicate drivers
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from driver_service.auth import (
    AuthContext,
    internal_service_auth_dependency,
    issue_internal_service_token,
)
from driver_service.config import settings
from driver_service.database import get_session
from driver_service.enums import AuditActionType
from driver_service.errors import (
    driver_forbidden,
    driver_hard_delete_blocked_by_history,
    driver_merge_source_equals_target,
    driver_merge_source_has_active_trips,
    driver_not_found,
    driver_trip_check_unavailable,
    driver_validation_error,
)
from driver_service.models import (
    DriverAuditLogModel,
    DriverMergeHistoryModel,
    DriverModel,
    DriverOutboxModel,
)
from driver_service.observability import correlation_id
from driver_service.schemas import MergeDriversRequest
from driver_service.serializers import serialize_driver_admin

logger = logging.getLogger("driver_service")
router = APIRouter(prefix="/internal/v1/drivers", tags=["driver-maintenance"])

_http_client: httpx.AsyncClient | None = None
_http_client_lock = asyncio.Lock()


async def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is not None:
        return _http_client
    async with _http_client_lock:
        if _http_client is None:
            _http_client = httpx.AsyncClient(timeout=settings.dependency_timeout_seconds)
    return _http_client


async def close_http_client() -> None:
    global _http_client
    client = _http_client
    _http_client = None
    if client is not None:
        await client.aclose()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _new_ulid() -> str:
    return str(ULID())


async def _write_outbox(session: AsyncSession, driver_id: str, event_name: str, payload: dict[str, Any]) -> None:
    outbox = DriverOutboxModel(
        outbox_id=_new_ulid(),
        aggregate_type="DRIVER",
        aggregate_id=driver_id,
        aggregate_version=1,
        driver_id=driver_id,
        event_name=event_name,
        event_version=1,
        payload_json=json.dumps(payload),
        publish_status="PENDING",
        attempt_count=0,
        created_at_utc=_now_utc(),
        next_attempt_at_utc=_now_utc(),
    )
    session.add(outbox)


async def _check_trip_references(driver_id: str) -> bool:
    """Check with Trip Service if driver has active trips.

    Returns True if safe to delete (no active trips), False if blocked.
    """
    token = await issue_internal_service_token()
    url = f"{settings.trip_service_base_url}/internal/v1/assets/reference-check"
    payload = {"asset_id": driver_id, "asset_type": "DRIVER"}

    try:
        client = await _get_http_client()
        headers = {"Authorization": f"Bearer {token}"}
        if c_id := correlation_id.get():
            headers["X-Correlation-ID"] = c_id

        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            # is_referenced=True means there ARE active trips, so NOT safe to delete
            return not data.get("is_referenced", True)

        # Trip service returned error — fail closed (unsafe)
        logger.error("Trip Service reference check failed: %d %s", resp.status_code, resp.text)
        return False
    except Exception:
        logger.exception("Connectivity error during Trip Service reference check")
        raise driver_trip_check_unavailable()


# ---------------------------------------------------------------------------
# POST /internal/v1/drivers/{driver_id}/hard-delete
# ---------------------------------------------------------------------------


@router.post("/{driver_id}/hard-delete", status_code=200)
async def hard_delete_driver(
    driver_id: str,
    request: Request,
    auth: AuthContext = Depends(internal_service_auth_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Permanently delete a driver record (spec §3.14).

    Feature-flagged. Must be soft-deleted first. Checks Trip Service for references.
    """
    if not settings.enable_hard_delete:
        raise driver_forbidden("Hard delete is not enabled.")

    request_id = getattr(request.state, "request_id", None)
    now = _now_utc()

    result = await session.execute(select(DriverModel).where(DriverModel.driver_id == driver_id))
    driver = result.scalar_one_or_none()
    if not driver:
        raise driver_not_found(driver_id)

    # Must be soft-deleted first
    if driver.soft_deleted_at_utc is None:
        raise driver_validation_error("Driver must be soft-deleted before hard delete.")

    # Check Trip Service for references
    safe = await _check_trip_references(driver_id)
    if not safe:
        raise driver_hard_delete_blocked_by_history()

    # Capture snapshot before deletion
    old_snapshot = serialize_driver_admin(driver)

    # Write audit BEFORE deleting (audit survives hard delete)
    audit = DriverAuditLogModel(
        audit_id=_new_ulid(),
        driver_id=driver_id,
        action_type=AuditActionType.HARD_DELETE.value,
        old_snapshot_json=json.dumps(old_snapshot),
        actor_id=auth.actor_id,
        actor_role=auth.role,
        reason="Permanent deletion",
        request_id=request_id,
        created_at_utc=now,
    )
    session.add(audit)

    # Write outbox event
    await _write_outbox(
        session,
        driver_id,
        "driver.hard_deleted.v1",
        {
            "driver_id": driver_id,
            "deleted_at_utc": now.isoformat(),
        },
    )

    # Delete the record
    await session.delete(driver)
    await session.commit()

    return {"driver_id": driver_id, "status": "HARD_DELETED", "deleted_at_utc": now.isoformat()}


# ---------------------------------------------------------------------------
# POST /internal/v1/drivers/merge
# ---------------------------------------------------------------------------


@router.post("/merge", status_code=200)
async def merge_drivers(
    body: MergeDriversRequest,
    request: Request,
    auth: AuthContext = Depends(internal_service_auth_dependency),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Merge a source driver into a target driver (spec §3.15).

    Feature-flagged. Source is soft-deleted after merge. Deterministic lock order.
    """
    if not settings.enable_merge_endpoint:
        raise driver_forbidden("Merge endpoint is not enabled.")

    if body.source_driver_id == body.target_driver_id:
        raise driver_merge_source_equals_target()

    request_id = getattr(request.state, "request_id", None)
    now = _now_utc()

    # Deterministic lock order (smaller ID first)
    first_id, second_id = sorted([body.source_driver_id, body.target_driver_id])

    result1 = await session.execute(select(DriverModel).where(DriverModel.driver_id == first_id).with_for_update())
    result2 = await session.execute(select(DriverModel).where(DriverModel.driver_id == second_id).with_for_update())

    driver1 = result1.scalar_one_or_none()
    driver2 = result2.scalar_one_or_none()

    if not driver1 or not driver2:
        missing_id = first_id if not driver1 else second_id
        raise driver_not_found(missing_id)

    source = driver1 if driver1.driver_id == body.source_driver_id else driver2
    target = driver1 if driver1.driver_id == body.target_driver_id else driver2

    # Check trip references on source
    safe = await _check_trip_references(source.driver_id)
    if not safe:
        raise driver_merge_source_has_active_trips()

    # Capture OLD snapshots before mutation
    old_source_snapshot = serialize_driver_admin(source)
    old_target_snapshot = serialize_driver_admin(target)

    # Soft-delete the source
    source.soft_deleted_at_utc = now
    source.soft_deleted_by_actor_id = auth.actor_id
    source.soft_delete_reason = f"Merged into {target.driver_id}"
    source.row_version += 1
    source.updated_at_utc = now
    source.updated_by_actor_id = auth.actor_id

    # Update target version
    target.row_version += 1
    target.updated_at_utc = now
    target.updated_by_actor_id = auth.actor_id

    # Write merge history
    merge_record = DriverMergeHistoryModel(
        merge_id=_new_ulid(),
        source_driver_id=source.driver_id,
        target_driver_id=target.driver_id,
        merge_reason=body.reason,
        actor_id=auth.actor_id,
        actor_role=auth.role,
        request_id=request_id or "",
        merged_at_utc=now,
    )
    session.add(merge_record)

    # Capture NEW snapshots after mutation
    new_source_snapshot = serialize_driver_admin(source)
    new_target_snapshot = serialize_driver_admin(target)

    # Audit for both source and target with both snapshots
    for driver_obj, action, old_snap, new_snap in [
        (source, "MERGE_SOURCE", old_source_snapshot, new_source_snapshot),
        (target, "MERGE_TARGET", old_target_snapshot, new_target_snapshot),
    ]:
        audit = DriverAuditLogModel(
            audit_id=_new_ulid(),
            driver_id=driver_obj.driver_id,
            action_type=AuditActionType.MERGE.value,
            changed_fields_json=json.dumps(
                {
                    "merge_role": action,
                    "source_driver_id": source.driver_id,
                    "target_driver_id": target.driver_id,
                }
            ),
            old_snapshot_json=json.dumps(old_snap) if old_snap else None,
            new_snapshot_json=json.dumps(new_snap) if new_snap else None,
            actor_id=auth.actor_id,
            actor_role=auth.role,
            reason=body.reason,
            request_id=request_id,
            created_at_utc=now,
        )
        session.add(audit)

    # Outbox event
    await _write_outbox(
        session,
        source.driver_id,
        "driver.merged.v1",
        {
            "source_driver_id": source.driver_id,
            "target_driver_id": target.driver_id,
            "reason": body.reason,
            "merged_at_utc": now.isoformat(),
        },
    )

    await session.commit()

    return {
        "merge_id": merge_record.merge_id,
        "source_driver_id": source.driver_id,
        "target_driver_id": target.driver_id,
        "source_status": "SOFT_DELETED",
        "merged_at_utc": now.isoformat(),
    }
