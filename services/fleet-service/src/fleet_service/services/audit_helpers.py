"""Shared high-fidelity audit helpers for Fleet Service."""

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from fleet_service.models import FleetAuditLogModel, FleetTrailer, FleetVehicle
from fleet_service.timestamps import utc_now_aware


def serialize_vehicle_admin(vehicle: FleetVehicle) -> Dict[str, Any]:
    """Serialize a vehicle for high-fidelity audit snapshots."""
    return {
        "vehicle_id": vehicle.vehicle_id,
        "asset_code": vehicle.asset_code,
        "plate_raw": vehicle.plate_raw_current,
        "normalized_plate": vehicle.normalized_plate_current,
        "brand": vehicle.brand,
        "model": vehicle.model,
        "model_year": vehicle.model_year,
        "ownership_type": vehicle.ownership_type,
        "status": vehicle.status,
        "notes": vehicle.notes,
        "row_version": vehicle.row_version,
        "created_at_utc": vehicle.created_at_utc.isoformat() if vehicle.created_at_utc else None,
        "updated_at_utc": vehicle.updated_at_utc.isoformat() if vehicle.updated_at_utc else None,
    }


def serialize_trailer_admin(trailer: FleetTrailer) -> Dict[str, Any]:
    """Serialize a trailer for high-fidelity audit snapshots."""
    return {
        "trailer_id": trailer.trailer_id,
        "asset_code": trailer.asset_code,
        "plate_raw": trailer.plate_raw_current,
        "normalized_plate": trailer.normalized_plate_current,
        "brand": trailer.brand,
        "model": trailer.model,
        "model_year": trailer.model_year,
        "ownership_type": trailer.ownership_type,
        "status": trailer.status,
        "notes": trailer.notes,
        "row_version": trailer.row_version,
        "created_at_utc": trailer.created_at_utc.isoformat() if trailer.created_at_utc else None,
        "updated_at_utc": trailer.updated_at_utc.isoformat() if trailer.updated_at_utc else None,
    }


async def _write_fleet_audit(
    session: AsyncSession,
    *,
    aggregate_type: str,
    aggregate_id: str,
    action_type: str,
    actor_id: str,
    actor_role: str,
    old_snapshot: Dict[str, Any] | None = None,
    new_snapshot: Dict[str, Any] | None = None,
    changed_fields: Dict[str, Any] | None = None,
    reason: str | None = None,
    request_id: str | None = None,
) -> None:
    """Write a high-fidelity audit log entry for a fleet asset mutation."""
    audit_id = str(ULID())
    session.add(
        FleetAuditLogModel(
            audit_id=audit_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            action_type=action_type,
            old_snapshot_json=old_snapshot,
            new_snapshot_json=new_snapshot,
            changed_fields_json=changed_fields,
            actor_id=actor_id,
            actor_role=actor_role,
            reason=reason,
            request_id=request_id,
            created_at_utc=utc_now_aware(),
        )
    )
