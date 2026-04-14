"""Hardened outbox relay worker for Driver Service — standardized to platform-common."""

from __future__ import annotations

import json
import logging
from typing import Any

from platform_common import MessageBroker, OutboxMessage, OutboxRelayBase, RobustJSONEncoder

from driver_service.database import async_session_factory
from driver_service.models import DriverOutboxModel

logger = logging.getLogger("driver_service.outbox_relay")


class DriverOutboxRelay(OutboxRelayBase):  # type: ignore[misc]
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

        # Serialize payload using the robust encoder (BUG-002 fix)
        payload_dict = row.payload_json if isinstance(row.payload_json, dict) else json.loads(row.payload_json)
        payload_str = json.dumps(payload_dict, cls=RobustJSONEncoder)

        return OutboxMessage(
            event_id=str(row.outbox_id),
            event_name=row.event_name,
            partition_key=partition_key,
            payload=payload_str,
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
