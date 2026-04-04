"""Delete audit repository (Section 8.7 — immutable hard-delete audit log)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.models import FleetAssetDeleteAudit


async def insert_delete_audit(session: AsyncSession, audit: FleetAssetDeleteAudit) -> None:
    """Insert a hard-delete audit row. Supports all 7 result paths."""
    session.add(audit)
    await session.flush()
