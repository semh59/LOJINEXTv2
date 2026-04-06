from sqlalchemy import inspect

from trip_service.models import TripOutbox
from trip_service.trip_helpers import _build_outbox_row


def debug_outbox():
    print("Checking TripOutbox columns...")
    mapper = inspect(TripOutbox)
    for column in mapper.attrs:
        print(f"Column: {column.key}")

    print("\nBuilding outbox row...")
    row = _build_outbox_row(
        trip_id="01KNHHY9H20HS5F46A942MTPT1",
        aggregate_version=1,
        event_name="trip.created.v1",
        payload={"test": "data"},
    )
    print(f"Row partition_key: {row.partition_key}")
    print(f"Row schema_version: {row.schema_version}")
    print(f"Row aggregate_type: {row.aggregate_type}")


if __name__ == "__main__":
    debug_outbox()
