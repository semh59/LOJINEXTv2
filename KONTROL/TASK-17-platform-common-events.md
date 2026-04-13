# TASK-17 — platform-common: Event Schema Kontratları

## Amaç
Servisler Kafka'ya event üretiyor ama event payload şemaları her serviste farklı yapıda. Consumer'lar yazmadan önce kontratları platform-common'da sabitle. Bu görev TASK-18/19/20 (consumer'lar) için ön koşul.

## Kapsam
```
packages/platform-common/src/platform_common/events.py  (YENİ)
packages/platform-common/src/platform_common/__init__.py
```

## Yeni dosya: events.py

```python
"""Canonical event envelope and payload contracts for LOJINEXTv2."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any


@dataclass(frozen=True)
class EventEnvelope:
    """Standard wrapper for all inter-service events."""
    event_id: str
    event_name: str
    event_version: int
    aggregate_type: str
    aggregate_id: str
    aggregate_version: int
    payload: dict[str, Any]
    published_at_utc: str  # ISO 8601
    correlation_id: str | None = None
    causation_id: str | None = None


# --- Trip Events ---
TRIP_CREATED_V1 = "trip.created.v1"
TRIP_COMPLETED_V1 = "trip.completed.v1"
TRIP_SOFT_DELETED_V1 = "trip.soft_deleted.v1"
TRIP_REJECTED_V1 = "trip.rejected.v1"
TRIP_HARD_DELETED_V1 = "trip.hard_deleted.v1"

# --- Driver Events ---
DRIVER_CREATED_V1 = "driver.created.v1"
DRIVER_UPDATED_V1 = "driver.updated.v1"
DRIVER_DEACTIVATED_V1 = "driver.deactivated.v1"

# --- Fleet Events ---
VEHICLE_CREATED_V1 = "vehicle.created.v1"
VEHICLE_UPDATED_V1 = "vehicle.updated.v1"
VEHICLE_DEACTIVATED_V1 = "vehicle.deactivated.v1"
TRAILER_CREATED_V1 = "trailer.created.v1"

# --- Location Events ---
ROUTE_RESOLVED_V1 = "route.resolved.v1"
ROUTE_PAIR_CREATED_V1 = "route_pair.created.v1"

# --- Identity Events ---
USER_CREATED_V1 = "user.created.v1"
USER_DEACTIVATED_V1 = "user.deactivated.v1"

# --- SAGA Compensation Events ---
SAGA_COMPENSATE_RELEASE_VEHICLE_V1 = "trip.compensate.release_vehicle.v1"
SAGA_COMPENSATE_RELEASE_DRIVER_V1 = "trip.compensate.release_driver.v1"
SAGA_COMPENSATE_MARK_FAILED_V1 = "trip.compensate.mark_failed.v1"


def parse_envelope(raw: dict[str, Any]) -> EventEnvelope:
    """Parse a raw Kafka message dict into an EventEnvelope."""
    return EventEnvelope(
        event_id=str(raw["event_id"]),
        event_name=str(raw["event_name"]),
        event_version=int(raw.get("event_version", 1)),
        aggregate_type=str(raw["aggregate_type"]),
        aggregate_id=str(raw["aggregate_id"]),
        aggregate_version=int(raw.get("aggregate_version", 1)),
        payload=raw.get("data") or raw.get("payload") or {},
        published_at_utc=str(raw.get("published_at_utc", "")),
        correlation_id=raw.get("correlation_id"),
        causation_id=raw.get("causation_id"),
    )
```

## __init__.py güncelleme

```python
from .events import (
    EventEnvelope,
    parse_envelope,
    TRIP_CREATED_V1,
    TRIP_COMPLETED_V1,
    TRIP_SOFT_DELETED_V1,
    DRIVER_CREATED_V1,
    VEHICLE_CREATED_V1,
    ROUTE_RESOLVED_V1,
    USER_CREATED_V1,
    SAGA_COMPENSATE_RELEASE_VEHICLE_V1,
    SAGA_COMPENSATE_RELEASE_DRIVER_V1,
    SAGA_COMPENSATE_MARK_FAILED_V1,
)

__all__ = [
    "OutboxPublishStatus",
    "StateMachine",
    "compute_data_quality_flag",
    "EventEnvelope",
    "parse_envelope",
    # event name constants...
]
```

## Doğrulama
```bash
python -c "from platform_common.events import EventEnvelope, parse_envelope, TRIP_CREATED_V1; print('OK')"
```

## Tamamlanma kriterleri
- [ ] `events.py` oluşturuldu
- [ ] `EventEnvelope` dataclass tanımlı
- [ ] Tüm event name sabitleri var
- [ ] `parse_envelope()` fonksiyonu var
- [ ] `__init__.py` export'ları güncellendi
- [ ] Syntax error yok
