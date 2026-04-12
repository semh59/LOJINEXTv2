"""Hardened outbox relay worker for Fleet Service — standardized to platform-common."""

from __future__ import annotations

import logging
from typing import Any

from fleet_service.database import async_session_factory
from fleet_service.models import FleetOutbox
from platform_common import OutboxRelayBase, MessageBroker, OutboxMessage

logger = logging.getLogger("fleet_service.outbox_relay")


class FleetOutboxRelay(OutboxRelayBase):
    """Fleet-specific implementation of the canonical outbox relay."""

    def __init__(
        self,
        broker: MessageBroker,
        batch_size: int = 20,
    ):
        super().__init__(
            model_class=FleetOutbox,
            broker=broker,
            session_factory=async_session_factory,
            batch_size=batch_size,
        )

    def map_row_to_message(self, row: FleetOutbox) -> OutboxMessage:
        """Map FleetOutbox row to the canonical OutboxMessage."""
        import json

        # fleet-service outbox stores payload as a JSON string in payload_json
        payload = json.loads(row.payload_json) if isinstance(row.payload_json, str) else row.payload_json

        return OutboxMessage(
            event_id=str(row.outbox_id),
            event_name=row.event_name,
            partition_key=row.aggregate_id,
            payload=payload,
            schema_version=row.event_version,
            aggregate_type=row.aggregate_type,
            aggregate_id=str(row.aggregate_id),
            causation_id=row.causation_id,
            correlation_id=row.correlation_id,
        )


async def run_outbox_relay(broker: MessageBroker, shutdown_event: Any = None) -> None:
    """Entry point for the fleet outbox relay worker."""
    relay = FleetOutboxRelay(broker=broker)
    await relay.run(shutdown_event=shutdown_event)
