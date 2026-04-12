"""Hardened outbox relay worker for Trip Service — standardized to platform-common."""

from __future__ import annotations

import json
import logging
from typing import Any

from trip_service.database import async_session_factory
from trip_service.models import TripOutbox
from platform_common import OutboxRelayBase, MessageBroker, OutboxMessage, RobustJSONEncoder

logger = logging.getLogger("trip_service.outbox_relay")


class TripOutboxRelay(OutboxRelayBase):
    """Trip-specific implementation of the canonical outbox relay."""

    def __init__(
        self,
        broker: MessageBroker,
        batch_size: int = 50,
    ):
        super().__init__(
            model_class=TripOutbox,
            broker=broker,
            session_factory=async_session_factory,
            batch_size=batch_size,
        )

    def map_row_to_message(self, row: TripOutbox) -> OutboxMessage:
        """Map TripOutbox row to the canonical OutboxMessage."""

        # Serialize payload using the robust encoder
        payload_dict = json.loads(row.payload_json) if isinstance(row.payload_json, str) else row.payload_json
        payload_str = json.dumps(payload_dict, cls=RobustJSONEncoder)

        return OutboxMessage(
            event_id=str(row.event_id),
            event_name=row.event_name,
            partition_key=row.partition_key,
            payload=payload_str,
            schema_version=row.schema_version,
            aggregate_type=row.aggregate_type,
            aggregate_id=str(row.aggregate_id),
            correlation_id=row.correlation_id,
            causation_id=row.causation_id,
        )


async def run_outbox_relay(broker: MessageBroker, shutdown_event: Any = None) -> None:
    """Entry point for the trip outbox relay worker."""
    from trip_service.config import settings

    relay = TripOutboxRelay(
        broker=broker, batch_size=settings.outbox_relay_max_retry_count
    )  # batch_size logic varies per service
    await relay.run(shutdown_event=shutdown_event)
