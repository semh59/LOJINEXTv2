"""Hardened outbox relay worker for Auth Service ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â standardized to platform-common."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from auth_service.database import async_session_factory
from auth_service.models import AuthOutboxModel, AuthWorkerHeartbeatModel
from platform_common import OutboxRelayBase, MessageBroker, OutboxMessage, RobustJSONEncoder

from datetime import datetime, UTC
from sqlalchemy.dialects.postgresql import insert

logger = logging.getLogger("auth_service.outbox_relay")
OUTBOX_WORKER_NAME = "auth_outbox_relay"


class AuthOutboxRelay(OutboxRelayBase):
    """Auth-specific implementation of the canonical outbox relay.
    
    Delegates to platform-common OutboxRelayBase which correctly handles:
    - Dead-letter counter must check for actual DEAD_LETTER status, ensuring
      publish_status == "DEAD_LETTER" instead of legacy null payload checks.
    """

    def __init__(
        self,
        broker: MessageBroker,
        batch_size: int = 20,
    ):
        super().__init__(
            model_class=AuthOutboxModel,
            broker=broker,
            session_factory=async_session_factory,
            batch_size=batch_size,
        )

    async def _heartbeat(self) -> None:
        """Standardized heartbeat for forensic certification."""
        try:
            async with async_session_factory() as session:
                stmt = (
                    insert(AuthWorkerHeartbeatModel)
                    .values(worker_name=OUTBOX_WORKER_NAME, last_seen_at_utc=datetime.now(UTC))
                    .on_conflict_do_update(
                        index_elements=["worker_name"], set_={"last_seen_at_utc": datetime.now(UTC)}
                    )
                )
                await session.execute(stmt)
                await session.commit()
        except Exception:
            logger.exception("Failed to heartbeat in AuthOutboxRelay")

    async def run(self, shutdown_event: Any = None) -> None:
        """Extended run loop with heartbeat for certified readiness."""
        logger.info("Starting outbox relay with forensic heartbeat: %s", OUTBOX_WORKER_NAME)
        while not (shutdown_event and shutdown_event.is_set()):
            await self._heartbeat()
            await self.process_batch()
            await asyncio.sleep(self.poll_interval_seconds)

    def map_row_to_message(self, row: AuthOutboxModel) -> OutboxMessage:
        """Map AuthOutboxModel row to the canonical OutboxMessage."""

        # Serialize payload using the robust encoder
        payload_dict = (
            json.loads(row.payload_json) if isinstance(row.payload_json, str) else row.payload_json
        )
        payload_str = json.dumps(payload_dict, cls=RobustJSONEncoder)

        return OutboxMessage(
            event_id=str(row.outbox_id),
            event_name=row.event_name,
            partition_key=row.partition_key,
            payload=payload_str,
            schema_version=row.event_version,
            aggregate_type=row.aggregate_type,
            aggregate_id=str(row.aggregate_id),
            causation_id=row.causation_id,
            correlation_id=row.correlation_id,
        )


async def run_outbox_relay(broker: MessageBroker, shutdown_event: Any = None) -> None:
    """Entry point for the identity outbox relay worker."""
    relay = AuthOutboxRelay(broker=broker)
    await relay.run(shutdown_event=shutdown_event)
