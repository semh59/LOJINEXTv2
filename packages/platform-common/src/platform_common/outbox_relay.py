"""Canonical Outbox Relay Base for all LOJINEXT services.

Provides a generic framework for:
- Claiming batches of outbox events (FOR UPDATE SKIP LOCKED).
- Head-of-Line (HOL) blocking for sequential processing.
- Multi-instance safe processing.
- Error handling and dead-lettering.

This module should be subclassed or used as a template in specific services.
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, TypeVar, Generic, Sequence

from sqlalchemy import and_, not_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from platform_common.broker import MessageBroker, OutboxMessage
from platform_common.outbox import OutboxPublishStatus

logger = logging.getLogger("platform_common.outbox_relay")

T = TypeVar("T")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class OutboxRelayBase:
    """Generic base for outbox relay workers.

    Services should instantiate this with their specific model class and
    configuration.
    """

    def __init__(
        self,
        model_class: Any,
        broker: MessageBroker,
        session_factory: Callable[[], AsyncSession],
        batch_size: int = 20,
        claim_ttl_seconds: int = 60,
        max_failures: int = 10,
        poll_interval_seconds: float = 5.0,
        metrics_callback: Callable[[str, str, Any], None] | None = None,
    ):
        self.model_class = model_class
        self.broker = broker
        self.session_factory = session_factory
        self.batch_size = batch_size
        self.claim_ttl_seconds = claim_ttl_seconds
        self.max_failures = max_failures
        self.poll_interval_seconds = poll_interval_seconds
        self.metrics_callback = metrics_callback
        self.worker_id = f"relay-{uuid.uuid4().hex[:8]}"

    async def run(self, shutdown_event: asyncio.Event | None = None) -> None:
        """Main loop."""
        logger.info(
            "Starting outbox relay for %s (worker_id=%s)",
            self.model_class.__name__,
            self.worker_id,
        )

        while True:
            if shutdown_event and shutdown_event.is_set():
                logger.info("Shutdown signal received, exiting.")
                return

            try:
                await self.process_batch()
            except Exception:
                logger.exception("Error in outbox relay loop")

            await asyncio.sleep(self.poll_interval_seconds)

    async def process_batch(self) -> int:
        """Process one batch of events with controlled concurrency."""
        claim_token, event_ids = await self._claim_batch()
        if not event_ids:
            return 0

        # Elite Hardening: Limit concurrent publishing to prevent local task starvation
        # and respect Kafka producer back-pressure.
        sem = asyncio.Semaphore(10)  # Max 10 concurrent publishes per worker instance

        async def _safe_publish(eid):
            async with sem:
                try:
                    return await self._publish_single(eid, claim_token)
                except Exception:
                    logger.exception("Task error in outbox event %s", eid)
                    return False

        results = await asyncio.gather(*[_safe_publish(eid) for eid in event_ids])
        published_count = sum(1 for r in results if r)

        if published_count == self.batch_size:
            # High load detected: skip sleep to clear backlog faster,
            # but preserve a small yield for event loop health.
            await asyncio.sleep(0.01)

        return published_count

    async def _claim_batch(self) -> tuple[str, list[str]]:
        """Claim a batch of eligible rows."""
        now = _now_utc()
        claim_token = str(uuid.uuid4())
        claim_ttl = timedelta(seconds=self.claim_ttl_seconds)

        async with self.session_factory() as session:
            m1 = aliased(self.model_class)
            m2 = aliased(self.model_class)

            # HOL blocking logic: Earliest non-published row wins.
            # Assumes model has 'partition_key', 'publish_status', 'created_at_utc'
            hol_subq = select(1).where(
                m2.partition_key == m1.partition_key,
                m2.publish_status != OutboxPublishStatus.PUBLISHED.value,
                m2.created_at_utc < m1.created_at_utc,
            )

            # Find candidates: PENDING/FAILED or expired PUBLISHING
            # Assumes model has 'outbox_id' or 'event_id' as PK
            pk_col = getattr(m1, "outbox_id", getattr(m1, "event_id", None))
            if pk_col is None:
                raise AttributeError(f"Model {self.model_class} must have outbox_id or event_id")

            stmt = (
                select(pk_col)
                .where(
                    or_(
                        m1.publish_status.in_(
                            [
                                OutboxPublishStatus.PENDING.value,
                                OutboxPublishStatus.READY.value,
                                OutboxPublishStatus.FAILED.value,
                            ]
                        ),
                        and_(
                            m1.publish_status == OutboxPublishStatus.PUBLISHING.value,
                            m1.claim_expires_at_utc < now,
                        ),
                    ),
                    m1.next_attempt_at_utc.is_(None) | (m1.next_attempt_at_utc <= now),
                    not_(hol_subq.exists()),
                )
                .order_by(m1.created_at_utc.asc())
                .with_for_update(skip_locked=True)
                .limit(self.batch_size)
            )

            result = await session.execute(stmt)
            ids = [str(i) for i in result.scalars().all()]

            if not ids:
                return claim_token, []

            # Update claimed rows
            stmt_update = (
                update(self.model_class)
                .where(pk_col.in_(ids))
                .values(
                    publish_status=OutboxPublishStatus.PUBLISHING.value,
                    claim_token=claim_token,
                    claim_expires_at_utc=now + claim_ttl,
                    claimed_by_worker=self.worker_id,
                )
            )
            await session.execute(stmt_update)
            await session.commit()
            return claim_token, ids

    async def _publish_single(self, event_id: str, claim_token: str) -> bool:
        """Internal helper to publish a single event."""
        # This part requires mapping row fields to OutboxMessage.
        # Since models vary, we should probably have a 'map_row_to_message' method
        # that can be overridden by subclasses.
        async with self.session_factory() as session:
            pk_col = getattr(
                self.model_class, "outbox_id", getattr(self.model_class, "event_id", None)
            )
            row = (
                await session.execute(
                    select(self.model_class).where(
                        pk_col == event_id,
                        self.model_class.claim_token == claim_token,
                    )
                )
            ).scalar_one_or_none()

            if not row:
                return False

            message = self.map_row_to_message(row)
            try:
                await self.broker.publish(message)
                await self._mark_published(session, row)
                if self.metrics_callback:
                    self.metrics_callback("success", message.event_name, None)
                return True
            except Exception as exc:
                await self._mark_failed(session, row, exc)
                if self.metrics_callback:
                    self.metrics_callback("failure", message.event_name, exc)
                return False

    def map_row_to_message(self, row: Any) -> OutboxMessage:
        """Map generic model row to canonical OutboxMessage.

        Subclasses should override this if model fields differ from defaults.
        """
        # Attempt to map common fields
        return OutboxMessage(
            event_id=str(getattr(row, "outbox_id", getattr(row, "event_id"))),
            event_name=row.event_name,
            partition_key=row.partition_key,
            payload=row.payload_json,
            schema_version=getattr(row, "schema_version", 1),
            aggregate_type=row.aggregate_type,
            aggregate_id=row.aggregate_id,
            causation_id=getattr(row, "causation_id", None),
            correlation_id=getattr(row, "correlation_id", None),
        )

    async def _mark_published(self, session: AsyncSession, row: Any) -> None:
        """Mark row as published and commit."""
        row.publish_status = OutboxPublishStatus.PUBLISHED.value
        row.published_at_utc = _now_utc()
        row.claim_token = None
        row.claim_expires_at_utc = None
        row.claimed_by_worker = None
        row.attempt_count = 0
        await session.commit()

    async def _mark_failed(self, session: AsyncSession, row: Any, exc: Exception) -> None:
        """Handle failure, update attempt count and potentially dead-letter."""
        row.attempt_count += 1
        row.last_error_code = str(exc)[:100]
        row.claim_token = None
        row.claim_expires_at_utc = None
        row.claimed_by_worker = None

        if row.attempt_count >= self.max_failures:
            row.publish_status = OutboxPublishStatus.DEAD_LETTER.value
            logger.error(
                "Outbox event %s dead-lettered after %d attempts", row.event_name, row.attempt_count
            )
        else:
            row.publish_status = OutboxPublishStatus.FAILED.value
            # Simple exponential backoff: 2^attempt * 5s
            delay = (2**row.attempt_count) * 5
            row.next_attempt_at_utc = _now_utc() + timedelta(seconds=delay)

        await session.commit()
