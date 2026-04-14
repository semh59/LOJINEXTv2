import json
import logging
from typing import Any

from platform_common import utc_now
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trip_service.models import TripSagaRecord, TripTrip
from trip_service.trip_helpers import _write_outbox

logger = logging.getLogger("trip_service.saga")


class TripSagaCoordinator:
    """Manages the State Machine for Trip Creation / Assignment."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def start_saga(self, trip_id: str) -> None:
        """Initialize the SAGA when a trip is created."""
        record = TripSagaRecord(
            id=f"SAGA-{trip_id}",
            trip_id=trip_id,
            saga_status="PENDING",
            current_step="RESERVING_DRIVER",
            created_at_utc=utc_now(),
            updated_at_utc=utc_now(),
        )
        self.session.add(record)
        # Event Outboxing to Driver Service
        await _write_outbox(
            self.session,
            trip_id=trip_id,
            event_name="driver.reserve.command",
            payload={"trip_id": trip_id, "command": "reserve_driver"}
        )
        logger.info(f"SAGA started for trip {trip_id}, step: RESERVING_DRIVER")

    async def handle_event(self, event_name: str, payload: dict[str, Any]) -> None:
        """Advance the SAGA state based on domain events."""
        trip_id = payload.get("trip_id")
        if not trip_id:
            return

        result = await self.session.execute(select(TripSagaRecord).where(TripSagaRecord.trip_id == trip_id))
        record = result.scalar_one_or_none()

        if not record:
            logger.warning(f"Saga record not found for trip {trip_id}")
            return

        if event_name == "driver.reserved":
            if record.current_step == "RESERVING_DRIVER":
                record.current_step = "RESERVING_FLEET"
                record.updated_at_utc = utc_now()
                # Trigger Fleet Reservation
                await _write_outbox(
                    self.session,
                    trip_id=trip_id,
                    event_name="fleet.reserve.command",
                    payload={"trip_id": trip_id, "command": "reserve_fleet"}
                )
                logger.info(f"SAGA {trip_id}: Driver reserved, moving to RESERVING_FLEET")

        elif event_name == "fleet.vehicle.reserved":
            if record.current_step == "RESERVING_FLEET":
                record.current_step = "COMPLETED"
                record.saga_status = "COMPLETED"
                record.updated_at_utc = utc_now()
                logger.info(f"SAGA {trip_id}: Fleet reserved, SAGA COMPLETED")

                # Mark trip as assigned
                trip_res = await self.session.execute(select(TripTrip).where(TripTrip.id == trip_id))
                trip = trip_res.scalar_one_or_none()
                if trip:
                    trip.status = "ASSIGNED"
                await _write_outbox(
                    self.session,
                    trip_id=trip_id,
                    event_name="trip.assigned.v1",
                    payload={"trip_id": trip_id, "status": "ASSIGNED"}
                )

        elif event_name == "fleet.vehicle.failed":
            if record.current_step in ["RESERVING_FLEET", "RESERVING_DRIVER"]:
                await self.compensate(trip_id, "Fleet reservation failed")

    async def compensate(self, trip_id: str, reason: str) -> None:
        """Trigger compensation mechanisms."""
        result = await self.session.execute(select(TripSagaRecord).where(TripSagaRecord.trip_id == trip_id))
        record = result.scalar_one_or_none()
        if not record:
            return

        record.saga_status = "COMPENSATING"
        record.failures_json = json.dumps({"reason": reason})
        record.updated_at_utc = utc_now()

        # Issue driver.reservation.cancel command
        await _write_outbox(
            self.session,
            trip_id=trip_id,
            event_name="driver.cancel.command",
            payload={"trip_id": trip_id, "reason": reason}
        )
        logger.warning(f"SAGA {trip_id} COMPENSATING due to {reason}")

        trip_res = await self.session.execute(select(TripTrip).where(TripTrip.id == trip_id))
        trip = trip_res.scalar_one_or_none()
        if trip:
            trip.status = "CANCELLED"
            await _write_outbox(
                self.session,
                trip_id=trip_id,
                event_name="trip.cancelled.v1",
                payload={"trip_id": trip_id, "status": "CANCELLED", "reason": reason}
            )
