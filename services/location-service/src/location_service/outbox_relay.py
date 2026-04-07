"""Background relay for publishing Location Service outbox events to Kafka."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.broker import create_broker
from location_service.config import settings
from location_service.database import async_session_factory
from location_service.models import LocationOutboxModel
from location_service.observability import correlation_id

logger = logging.getLogger("location_service.outbox_relay")


class OutboxRelay:
    """Relays pending outbox events to the configured event broker."""

    def __init__(self) -> None:
        self.broker = create_broker()
        self.batch_size = settings.outbox_publish_batch_size
        self.claim_ttl_seconds = 60

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
        claim_expires = now + timedelta(seconds=self.claim_ttl_seconds)

        # 1. Fetch pending or stale-claimed events
        stmt = (
            select(LocationOutboxModel)
            .where(
                LocationOutboxModel.publish_status.in_(["PENDING", "FAILED"]),
                LocationOutboxModel.next_attempt_at_utc <= now,
                LocationOutboxModel.retry_count < settings.outbox_retry_max,
            )
            .order_by(LocationOutboxModel.next_attempt_at_utc.asc())
            .limit(self.batch_size)
            .with_for_update(skip_locked=True)
        )
        events = (await session.execute(stmt)).scalars().all()

        if not events:
            return []

        # 2. Mark as PUBLISHING in DB
        event_ids = [e.outbox_id for e in events]
        await session.execute(
            update(LocationOutboxModel)
            .where(LocationOutboxModel.outbox_id.in_(event_ids))
            .values(
                publish_status="PUBLISHING",
                claim_expires_at_utc=claim_expires,
            )
        )
        await session.commit()
        return list(events)

    async def _publish_event(self, event: LocationOutboxModel) -> bool:
        # Set correlation ID for tracing
        # The payload should ideally contain a correlation ID from the original request
        # but here we use a generated one or the one in context if available.
        cid = event.payload_json.get("correlation_id") or event.outbox_id
        token = correlation_id.set(cid)

        try:
            await self.broker.publish(
                topic=settings.kafka_topic,
                key=event.partition_key,
                payload=event.payload_json,
            )
            return True
        except Exception as exc:
            logger.error(
                "Failed to publish outbox event %s: %s",
                event.outbox_id,
                exc,
                extra={"event_name": event.event_name},
            )
            event.last_error_code = type(exc).__name__
            return False
        finally:
            correlation_id.reset(token)

    async def _update_event_status(self, session: AsyncSession, event: LocationOutboxModel, success: bool) -> None:
        now = datetime.now(UTC)
        if success:
            event.publish_status = "PUBLISHED"
            event.published_at_utc = now
        else:
            event.retry_count += 1
            if event.retry_count >= settings.outbox_retry_max:
                event.publish_status = "DEAD"
            else:
                event.publish_status = "FAILED"
                # Exponential backoff: 2, 4, 8, 16... minutes
                delay = 2**event.retry_count
                event.next_attempt_at_utc = now + timedelta(minutes=delay)

        await session.merge(event)
        await session.commit()

    async def close(self) -> None:
        await self.broker.close()


async def run_outbox_relay() -> None:
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
            try:
                processed = await relay.run_once()
                if processed == 0:
                    await asyncio.sleep(poll_interval)
            except Exception as exc:
                logger.error("Outbox relay loop error: %s", exc, exc_info=True)
                await asyncio.sleep(poll_interval)
    finally:
        await relay.close()
