"""Background relay for publishing Location Service outbox events to Kafka."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.broker import create_broker
from location_service.config import settings
from location_service.database import async_session_factory
from location_service.models import LocationOutboxModel
from location_service.observability import correlation_id

logger = logging.getLogger("location_service.outbox_relay")

WORKER_ID = f"location-outbox-{uuid.getnode()}"


class OutboxRelay:
    """Relays pending outbox events to the configured event broker."""

    def __init__(self) -> None:
        self.broker = create_broker()
        self.batch_size = settings.outbox_publish_batch_size
        self.claim_ttl = timedelta(minutes=5)

    async def run_once(self) -> int:
        """Process a single batch of pending outbox events."""
        async with async_session_factory() as session:
            events = await self._claim_batch(session)
            if not events:
                return 0

            processed_count = 0
            for event in events:
                success = await self._publish_event(event)
                await self._update_event_status(session, event, success)
                processed_count += 1

            return processed_count

    async def _claim_batch(self, session: AsyncSession) -> list[LocationOutboxModel]:
        now = datetime.now(UTC)
        claim_expires = now + self.claim_ttl
        claim_token = str(uuid.uuid4())

        from sqlalchemy import and_, or_
        from sqlalchemy.orm import aliased

        o2 = aliased(LocationOutboxModel)
        hol_subq = select(1).where(
            o2.partition_key == LocationOutboxModel.partition_key,
            o2.publish_status != "PUBLISHED",
            o2.created_at_utc < LocationOutboxModel.created_at_utc,
        )

        stmt = (
            select(LocationOutboxModel)
            .where(
                or_(
                    LocationOutboxModel.publish_status.in_(["PENDING", "FAILED"]),
                    and_(
                        LocationOutboxModel.publish_status == "PUBLISHING",
                        LocationOutboxModel.claim_expires_at_utc.is_not(None),
                        LocationOutboxModel.claim_expires_at_utc <= now,
                    ),
                ),
                LocationOutboxModel.next_attempt_at_utc <= now,
                LocationOutboxModel.attempt_count < settings.outbox_retry_max,
                ~hol_subq.exists(),
            )
            .order_by(LocationOutboxModel.created_at_utc.asc())
            .limit(self.batch_size)
            .with_for_update(skip_locked=True)
        )
        events = (await session.execute(stmt)).scalars().all()

        if not events:
            return []

        event_ids = [e.outbox_id for e in events]
        await session.execute(
            update(LocationOutboxModel)
            .where(LocationOutboxModel.outbox_id.in_(event_ids))
            .values(
                publish_status="PUBLISHING",
                claim_token=claim_token,
                claimed_by_worker=WORKER_ID,
                claim_expires_at_utc=claim_expires,
            )
        )
        await session.commit()
        return list(events)

    async def _publish_event(self, event: LocationOutboxModel) -> bool:
        payload = json.loads(event.payload_json) if isinstance(event.payload_json, str) else event.payload_json
        cid = payload.get("correlation_id") or event.outbox_id
        token = correlation_id.set(cid)

        try:
            await self.broker.publish(
                topic=settings.kafka_topic,
                key=event.aggregate_id,
                payload={
                    "event_id": event.outbox_id,
                    "event_name": event.event_name,
                    "event_version": event.event_version,
                    "aggregate_id": event.aggregate_id,
                    "aggregate_type": event.aggregate_type,
                    "aggregate_version": event.aggregate_version,
                    "payload": payload,
                    "published_at_utc": datetime.now(UTC).isoformat(),
                },
            )
            return True
        except Exception as exc:
            logger.error(
                "Failed to publish outbox event %s: %s",
                event.outbox_id,
                exc,
                extra={"event_name": event.event_name},
            )
            event.last_error_code = type(exc).__name__[:100]
            return False
        finally:
            correlation_id.reset(token)

    async def _update_event_status(self, session: AsyncSession, event: LocationOutboxModel, success: bool) -> None:
        now = datetime.now(UTC)
        if success:
            event.publish_status = "PUBLISHED"
            event.published_at_utc = now
            event.claim_expires_at_utc = None
            event.claim_token = None
            event.claimed_by_worker = None
        else:
            event.attempt_count += 1
            event.claim_expires_at_utc = None
            event.claim_token = None
            event.claimed_by_worker = None
            if event.attempt_count >= settings.outbox_retry_max:
                event.publish_status = "DEAD_LETTER"
            else:
                event.publish_status = "FAILED"
                backoff = min(2**event.attempt_count, 300)
                event.next_attempt_at_utc = now + timedelta(seconds=backoff)

        await session.merge(event)
        await session.commit()

    async def close(self) -> None:
        await self.broker.close()


async def run_outbox_relay(shutdown_event: asyncio.Event | None = None) -> None:
    """Infinite loop for the outbox relay worker."""
    relay = OutboxRelay()
    poll_interval = settings.outbox_poll_interval_seconds

    logger.info(
        "Location Outbox Relay starting",
        extra={
            "poll_interval": poll_interval,
            "batch_size": settings.outbox_publish_batch_size,
        },
    )

    try:
        while True:
            if shutdown_event and shutdown_event.is_set():
                logger.info("Outbox relay: shutdown signal received, exiting cleanly.")
                return

            try:
                processed = await relay.run_once()
                if processed == 0:
                    await asyncio.sleep(poll_interval)
            except Exception as exc:
                logger.error("Outbox relay loop error: %s", exc, exc_info=True)
                await asyncio.sleep(poll_interval)
    finally:
        await relay.close()
