"""Outbox relay worker for Identity Service."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.broker import EventBroker
from identity_service.config import settings
from identity_service.database import async_session_factory
from identity_service.models import IdentityOutboxModel, IdentityWorkerHeartbeatModel

logger = logging.getLogger("identity_service.outbox_relay")

OUTBOX_WORKER_NAME = "outbox_relay"


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _format_error(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {exc}"


async def record_worker_heartbeat(*, seen_at: datetime | None = None) -> None:
    """Persist the latest heartbeat for the outbox worker."""
    heartbeat_at = seen_at or _now_utc()
    async with async_session_factory() as session:
        heartbeat = await session.get(IdentityWorkerHeartbeatModel, OUTBOX_WORKER_NAME)
        if heartbeat is None:
            session.add(
                IdentityWorkerHeartbeatModel(
                    worker_name=OUTBOX_WORKER_NAME,
                    last_seen_at_utc=heartbeat_at,
                )
            )
        else:
            heartbeat.last_seen_at_utc = heartbeat_at
        await session.commit()


async def run_outbox_relay(broker: EventBroker) -> None:
    """Poll the outbox table and publish pending events to the broker."""
    logger.info(
        "Outbox relay worker started (poll_interval=%ds backend=%s)",
        settings.outbox_poll_interval_seconds,
        settings.resolved_broker_backend,
    )

    while True:
        try:
            await _process_batch(broker)
        except asyncio.CancelledError:
            logger.info("Outbox relay worker cancelled")
            return
        except Exception:  # noqa: BLE001
            logger.exception("Outbox relay error")

        try:
            await record_worker_heartbeat()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to record outbox worker heartbeat")

        await asyncio.sleep(settings.outbox_poll_interval_seconds)


async def _claim_batch(
    session: AsyncSession, *, now: datetime | None = None
) -> list[str]:
    """Claim a batch of outbox rows for publishing."""
    current_time = now or _now_utc()
    claim_expires_at = current_time + timedelta(
        seconds=settings.outbox_claim_ttl_seconds
    )
    query = (
        select(IdentityOutboxModel)
        .where(
            or_(
                IdentityOutboxModel.publish_status.in_(("PENDING", "FAILED")),
                and_(
                    IdentityOutboxModel.publish_status == "PUBLISHING",
                    IdentityOutboxModel.claim_expires_at_utc.is_not(None),
                    IdentityOutboxModel.claim_expires_at_utc <= current_time,
                ),
            ),
            IdentityOutboxModel.next_attempt_at_utc <= current_time,
        )
        .order_by(IdentityOutboxModel.created_at_utc.asc())
        .limit(settings.outbox_publish_batch_size)
        .with_for_update(skip_locked=True)
    )

    result = await session.execute(query)
    rows = result.scalars().all()
    if not rows:
        return []

    claimed_ids: list[str] = []
    for row in rows:
        row.publish_status = "PUBLISHING"
        row.claim_expires_at_utc = claim_expires_at
        row.last_error = None
        claimed_ids.append(row.outbox_id)

    await session.commit()
    return claimed_ids


async def _load_claimed_payload(
    outbox_id: str,
) -> tuple[str, dict[str, object]] | None:
    async with async_session_factory() as session:
        row = await session.get(IdentityOutboxModel, outbox_id)
        if row is None or row.publish_status != "PUBLISHING":
            return None
        payload = json.loads(row.payload_json)
        return (
            row.aggregate_id,
            {
                "event_name": row.event_name,
                "event_version": row.event_version,
                "aggregate_id": row.aggregate_id,
                "aggregate_type": row.aggregate_type,
                "data": payload,
                "published_at_utc": _now_utc().isoformat(),
            },
        )


async def _mark_published(outbox_id: str) -> None:
    async with async_session_factory() as session:
        row = await session.get(IdentityOutboxModel, outbox_id)
        if row is None:
            return
        row.publish_status = "PUBLISHED"
        row.published_at_utc = _now_utc()
        row.claim_expires_at_utc = None
        row.last_error = None
        row.next_attempt_at_utc = row.published_at_utc
        await session.commit()


async def _mark_publish_failure(outbox_id: str, exc: Exception) -> None:
    async with async_session_factory() as session:
        row = await session.get(IdentityOutboxModel, outbox_id)
        if row is None:
            return

        row.retry_count += 1
        row.claim_expires_at_utc = None
        row.last_error = _format_error(exc)
        now = _now_utc()
        if row.retry_count >= settings.outbox_retry_max:
            row.publish_status = "DEAD_LETTER"
            row.next_attempt_at_utc = now
            logger.error(
                "Outbox row %s moved to DEAD_LETTER after %d retries",
                row.outbox_id,
                row.retry_count,
            )
        else:
            row.publish_status = "FAILED"
            backoff = min(2**row.retry_count, 300)
            row.next_attempt_at_utc = now + timedelta(seconds=backoff)
        await session.commit()


async def _publish_claimed_row(outbox_id: str, broker: EventBroker) -> bool:
    """Publish a previously claimed row and finalize it in its own transaction."""
    from identity_service.observability import correlation_id

    token = correlation_id.set(outbox_id)
    try:
        payload = await _load_claimed_payload(outbox_id)
        if payload is None:
            return False

        key, event_payload = payload
        try:
            await broker.publish(
                topic=settings.kafka_topic,
                key=key,
                payload=event_payload,
            )
        except Exception as exc:  # noqa: BLE001
            await _mark_publish_failure(outbox_id, exc)
            return False

        await _mark_published(outbox_id)
        return True
    finally:
        correlation_id.reset(token)


async def _process_batch(broker: EventBroker) -> int:
    """Claim and publish one batch of outbox rows with per-event commits."""
    async with async_session_factory() as session:
        claimed_ids = await _claim_batch(session)

    if not claimed_ids:
        return 0

    published_count = 0
    for outbox_id in claimed_ids:
        if await _publish_claimed_row(outbox_id, broker):
            published_count += 1

    if claimed_ids:
        logger.info(
            "Outbox relay processed %d claimed rows (%d published)",
            len(claimed_ids),
            published_count,
        )
    return published_count
