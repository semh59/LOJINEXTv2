"""Shared high-fidelity audit and outbox helpers for Location Service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from location_service.models import LocationAuditLogModel, LocationOutboxModel, LocationPoint, RoutePair


def _new_ulid() -> str:
    return str(ULID())


def _now_utc() -> datetime:
    return datetime.now(UTC)


def serialize_point(point: LocationPoint) -> dict[str, Any]:
    """Serialize a LocationPoint for high-fidelity audit snapshots."""
    return {
        "location_id": str(point.location_id),
        "code": point.code,
        "name_tr": point.name_tr,
        "name_en": point.name_en,
        "normalized_name_tr": point.normalized_name_tr,
        "normalized_name_en": point.normalized_name_en,
        "latitude_6dp": point.latitude_6dp,
        "longitude_6dp": point.longitude_6dp,
        "is_active": point.is_active,
        "row_version": point.row_version,
        "created_at_utc": point.created_at_utc.isoformat() if point.created_at_utc else None,
        "updated_at_utc": point.updated_at_utc.isoformat() if point.updated_at_utc else None,
    }


def serialize_pair(pair: RoutePair) -> dict[str, Any]:
    """Serialize a RoutePair for high-fidelity audit snapshots."""
    return {
        "route_pair_id": str(pair.route_pair_id),
        "pair_code": pair.pair_code,
        "pair_status": pair.pair_status,
        "origin_location_id": str(pair.origin_location_id),
        "destination_location_id": str(pair.destination_location_id),
        "profile_code": pair.profile_code,
        "forward_route_id": str(pair.forward_route_id) if pair.forward_route_id else None,
        "reverse_route_id": str(pair.reverse_route_id) if pair.reverse_route_id else None,
        "current_active_forward_version_no": pair.current_active_forward_version_no,
        "current_active_reverse_version_no": pair.current_active_reverse_version_no,
        "pending_forward_version_no": pair.pending_forward_version_no,
        "pending_reverse_version_no": pair.pending_reverse_version_no,
        "row_version": pair.row_version,
        "created_at_utc": pair.created_at_utc.isoformat() if pair.created_at_utc else None,
        "updated_at_utc": pair.updated_at_utc.isoformat() if pair.updated_at_utc else None,
    }


async def _write_audit(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: str,
    action_type: str,
    actor_id: str,
    actor_role: str,
    old_snapshot: dict[str, Any] | None = None,
    new_snapshot: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> None:
    """Write a high-fidelity audit log entry for a location mutation."""
    audit = LocationAuditLogModel(
        audit_id=_new_ulid(),
        target_type=target_type,
        target_id=target_id,
        action_type=action_type,
        actor_id=actor_id,
        actor_role=actor_role,
        old_snapshot_json=old_snapshot,
        new_snapshot_json=new_snapshot,
        request_id=request_id,
        created_at_utc=_now_utc(),
    )
    session.add(audit)


async def _write_outbox(
    session: AsyncSession,
    *,
    event_name: str,
    payload: dict[str, Any],
) -> None:
    """Write a transactional outbox entry."""
    now = _now_utc()
    outbox = LocationOutboxModel(
        outbox_id=_new_ulid(),
        event_name=event_name,
        event_version=1,
        payload_json=payload,
        publish_status="PENDING",
        retry_count=0,
        created_at_utc=now,
        next_attempt_at_utc=now,
    )
    session.add(outbox)
