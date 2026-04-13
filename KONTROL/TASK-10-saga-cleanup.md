# TASK-10 — Saga.py Temizlik: 3 Sorun

## Amaç
`saga.py`'deki 3 ayrı sorunu düzelt: `__import__("json")` code smell, compensate her zaman FAILED status yapıyor, broker per-invocation create ediliyor.

## Kapsam
```
services/trip-service/src/trip_service/saga.py
```

## Değişiklik 1: __import__ kaldır

Dosyanın başına `import json` ekle:
```python
import json  # dosya başına ekle
```

Satır 64'teki `__import__("json").dumps(` → `json.dumps(` yap.

## Değişiklik 2: Compensate final status

Şu an her kompanzasyon sonucu FAILED yazıyor. Tüm adımlar OK ise COMPENSATED olmalı:

```python
# saga.py sonunda — _update_status çağrısından önce
steps_ok = all(
    await redis.hget(self.redis_key, f"step:{step.value}") == "OK"
    for step in _CompensateStep
)
final_status = SagaStatus.COMPENSATED if steps_ok else SagaStatus.FAILED
await self._update_status(final_status)
```

`SagaStatus` enum'una `COMPENSATED = "COMPENSATED"` ekle.

## Değişiklik 3: Broker injection

`__init__`'e broker parametresi ekle, her metoda yeni broker açma:

```python
class TripBookingSagaOrchestrator:
    def __init__(self, trip_id: str, broker: MessageBroker) -> None:
        self.trip_id = trip_id
        self.broker = broker   # inject edildi
        self.redis_key = f"saga:trip_booking:{trip_id}"

    async def start(self) -> None:
        await self._update_status(SagaStatus.PENDING)
        await self.broker.publish(...)   # create_broker() yok
        # finally: await broker.close() YOK — dışarıda yönetilir

    async def compensate(self, reason: str) -> None:
        await self._update_status(SagaStatus.COMPENSATING)
        # broker.close() YOK
        ...
```

## Tamamlanma kriterleri
- [ ] Dosya başında `import json` var
- [ ] `__import__("json")` yok
- [ ] `SagaStatus.COMPENSATED` var
- [ ] `compensate()` başarılı tamamlamada `COMPENSATED` yazıyor
- [ ] `__init__` broker parametresi alıyor
- [ ] `create_broker()` metod içinde çağrılmıyor
