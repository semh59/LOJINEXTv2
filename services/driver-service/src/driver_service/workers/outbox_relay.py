"""Hardened outbox relay worker for Driver Service — standardized to platform-common."""

from __future__ import annotations

import logging
from typing import Any

from driver_service.database import async_session_factory
from driver_service.models import DriverOutboxModel
from platform_common import OutboxRelayBase, MessageBroker, OutboxMessage

logger = logging.getLogger("driver_service.outbox_relay")


class DriverOutboxRelay(OutboxRelayBase):
    """Driver-specific implementation of the canonical outbox relay."""

    def __init__(
        self,
        broker: MessageBroker,
        batch_size: int = 20,
    ):
        super().__init__(
            model_class=DriverOutboxModel,
            broker=broker,
            session_factory=async_session_factory,
            batch_size=batch_size,
        )

    def map_row_to_message(self, row: DriverOutboxModel) -> OutboxMessage:
        """Map DriverOutboxModel specific fields to the canonical OutboxMessage."""
        # Note: driver-service uses DriverOutboxModel with some specific fields
        # like aggregate_version and driver_id. We map them appropriately.

        partition_key = row.partition_key or row.driver_id or "unknown"

        return OutboxMessage(
            event_id=str(row.event_id),
            event_name=row.event_name,
            partition_key=partition_key,
            payload=row.payload_json,
            schema_version=getattr(row, "event_version", 1),
            aggregate_type=row.aggregate_type,
            aggregate_id=str(row.aggregate_id),
            causation_id=row.causation_id,
            correlation_id=row.correlation_id,
        )


async def run_outbox_relay(broker: MessageBroker, shutdown_event: Any = None) -> None:
    """Entry point for the driver outbox relay worker."""
    relay = DriverOutboxRelay(broker=broker)
    await relay.run(shutdown_event=shutdown_event)
