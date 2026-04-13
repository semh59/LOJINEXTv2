# TASK-24 — Driver-Service: SAGA Compensation Consumer Aktivasyonu

## Amaç
TASK-19'da yazılan `_handle_release_driver` handler'ını gerçek iş mantığıyla doldur.

## Ön koşul
**TASK-19 tamamlanmış olmalı.**

## Kapsam
```
services/driver-service/src/driver_service/consumers/trip_events.py
```

## TASK-23 ile aynı pattern — driver domain

```python
async def _handle_release_driver(envelope) -> None:
    driver_id = envelope.payload.get("driver_id")
    trip_id = envelope.aggregate_id
    
    if not driver_id:
        logger.warning("release_driver event missing driver_id, skipping")
        return

    async with async_session_factory() as session:
        # Driver modeli incele — active_trip_id veya status alanı var mı?
        # Varsa güncelle
        
        # Outbox event üret: driver.released.v1
        outbox_row = DriverOutboxModel(
            event_id=str(ULID()),
            aggregate_type="DRIVER",
            aggregate_id=driver_id,
            event_name="driver.released.v1",
            event_version=1,
            payload_json=json.dumps({
                "driver_id": driver_id,
                "released_from_trip": trip_id,
                "reason": "SAGA_COMPENSATION",
            }),
            publish_status="PENDING",
            partition_key=driver_id,
            ...
        )
        session.add(outbox_row)
        await session.commit()
    
    logger.info("Driver %s released from trip %s via SAGA", driver_id, trip_id)
```

## Tamamlanma kriterleri
- [ ] `_handle_release_driver` gerçek DB işlemi yapıyor
- [ ] Compensation outbox event üretiyor
- [ ] Syntax error yok

---

# TASK-25 — Trip-Service: SAGA Orchestrator Gerçek Akışa Bağlama

## Amaç
`saga.py`'deki `TripBookingSagaOrchestrator` hiçbir yerde çağrılmıyor. TASK-10 ile broker injection düzeltildi. Bu görev orchestrator'ı trip oluşturma akışına bağlar.

## Ön koşul
**TASK-10, TASK-23, TASK-24 tamamlanmış olmalı.**

## Kapsam
```
services/trip-service/src/trip_service/service.py
services/trip-service/src/trip_service/saga.py
```

## Strateji

SAGA ne zaman başlatılır? Şu an trip oluşturma senkron ve atomik — outbox pattern ile güvende. SAGA en çok şu senaryoda anlam taşır: **trip oluşturuldu ama enrichment/validation downstream'de başarısız oldu ve kaynak serbest bırakılması gerekiyor**.

Şimdilik: trip hard-delete veya reject yapılırken SAGA compensation tetiklensin.

```python
# service.py — cancel_trip veya reject_trip içinde
from trip_service.saga import TripBookingSagaOrchestrator

async def reject_trip(self, trip_id: str, ...):
    ...
    # Mevcut reject mantığı
    
    # SAGA compensation: kaynakları serbest bırak
    saga = TripBookingSagaOrchestrator(
        trip_id=trip_id,
        broker=self.session.get_bind().app.state.broker  # ya da inject
    )
    asyncio.create_task(saga.compensate(reason=body.reason or "Trip rejected"))
    
    await self.session.commit()
```

## Broker erişimi

`TripService.__init__`'e broker parametresi ekle:

```python
class TripService:
    def __init__(self, session: AsyncSession, auth: AuthContext, broker: MessageBroker | None = None):
        self.session = session
        self.auth = auth
        self.broker = broker

# dependencies.py — get_trip_service
async def get_trip_service(
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(user_auth_dependency),
    request: Request = ...,
) -> TripService:
    broker = getattr(request.app.state, "broker", None)
    return TripService(session, auth, broker)
```

## Tamamlanma kriterleri
- [ ] `TripService` broker parametresi alıyor
- [ ] `reject_trip` veya `cancel_trip` içinde SAGA compensation tetikleniyor
- [ ] `TripBookingSagaOrchestrator` inject edilmiş broker kullanıyor (TASK-10)
- [ ] Syntax error yok
