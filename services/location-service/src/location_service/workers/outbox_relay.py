"""Hardened outbox relay worker for Location Service — standardized to platform-common."""

from __future__ import annotations

import json
import logging
from typing import Any

from location_service.database import async_session_factory
from location_service.models import LocationOutboxModel
from platform_common import MessageBroker, OutboxMessage, OutboxRelayBase, RobustJSONEncoder

logger = logging.getLogger("location_service.outbox_relay")


class LocationOutboxRelay(OutboxRelayBase):
    """Location-specific implementation of the canonical outbox relay."""

    def __init__(
        self,
        broker: MessageBroker,
        batch_size: int = 50,
    ):
        super().__init__(
            model_class=LocationOutboxModel,
            broker=broker,
            session_factory=async_session_factory,
            batch_size=batch_size,
        )

    def map_row_to_message(self, row: LocationOutboxModel) -> OutboxMessage:
        """Map LocationOutboxModel row to the canonical OutboxMessage."""

        # Serialize payload using the robust encoder
        payload_dict = json.loads(row.payload_json) if isinstance(row.payload_json, str) else row.payload_json
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
    """Entry point for the location outbox relay worker."""
    from location_service.config import settings

    relay = LocationOutboxRelay(broker=broker, batch_size=settings.outbox_publish_batch_size)
    await relay.run(shutdown_event=shutdown_event)
