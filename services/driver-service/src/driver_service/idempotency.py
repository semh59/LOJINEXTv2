"""Idempotency utilities for Driver Service de-duplication."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from driver_service.models import DriverIdempotencyRecordModel


def compute_endpoint_fingerprint(method: str, path: str) -> str:
    """Compute a stable fingerprint for an API endpoint."""
    return f"{method.upper()}:{path.lower()}"


def compute_request_hash(payload: dict[str, Any]) -> str:
    """Compute a SHA-256 hash of a normalized JSON payload."""
    serialized = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def check_idempotency(
    session: AsyncSession,
    idempotency_key: str,
    endpoint_fingerprint: str,
) -> DriverIdempotencyRecordModel | None:
    """Check if an idempotency key has already been processed for this endpoint."""
    result = await session.execute(
        select(DriverIdempotencyRecordModel).where(
            DriverIdempotencyRecordModel.idempotency_key == idempotency_key,
            DriverIdempotencyRecordModel.endpoint_fingerprint == endpoint_fingerprint,
        )
    )
    return result.scalar_one_or_none()


async def save_idempotency_record(
    session: AsyncSession,
    idempotency_key: str,
    endpoint_fingerprint: str,
    response_code: int,
    response_body: dict[str, Any] | None,
    actor_id: str,
    expiry_hours: int = 24,
) -> None:
    """Save an idempotency record to the database."""
    now = datetime.now(UTC)
    record = DriverIdempotencyRecordModel(
        idempotency_key=idempotency_key,
        endpoint_fingerprint=endpoint_fingerprint,
        response_code=response_code,
        response_body_json=json.dumps(response_body) if response_body else None,
        actor_id=actor_id,
        created_at_utc=now,
        expires_at_utc=now + timedelta(hours=expiry_hours),
    )
    session.add(record)


async def purge_expired_idempotency_records(session: AsyncSession) -> int:
    """Purge expired idempotency records from the database."""
    now = datetime.now(UTC)
    result = await session.execute(
        delete(DriverIdempotencyRecordModel).where(DriverIdempotencyRecordModel.expires_at_utc <= now)
    )
    return result.rowcount  # type: ignore[no-any-return]
