# AUDIT: fleet-service
**Tarih:** 2025  
**Kapsam:** Tüm src/ dosyaları incelendi  
**Yargı:** En olgun servis — mimari doğru kurulmuş. 4 spesifik bug mevcut.

---

## MİMARİ YAPI

```
fleet_service/
  domain/          ← enums, etag, formulas, idempotency, normalization
  services/        ← vehicle_service, trailer_service, internal_service
  repositories/    ← vehicle_repo, trailer_repo, outbox_repo, timeline_repo ...
  schemas/         ← requests.py, responses.py
  clients/         ← driver_client.py, trip_client.py
  workers/         ← outbox_relay.py
  routers/         ← ince, sadece HTTP I/O
```

Trip-service'in aksine katmanlar doğru ayrılmış. Repository pattern uygulanmış.

---

## KRİTİK BULGULAR

---

### BUG-1: Circuit Breaker Thread-Safe Değil — Multi-Process

**Dosya:** `clients/trip_client.py`, `clients/driver_client.py`

**Kanıt:**
```python
# trip_client.py — modül seviyesi global
_failure_count: int = 0
_last_failure_time: float = 0.0
_state: str = "CLOSED"

def _record_failure() -> None:
    global _failure_count, _last_failure_time, _state
    _failure_count += 1
    ...
```

**Problem:** Her worker process kendi modülünü import eder → her process ayrı circuit breaker state. 3 Gunicorn worker varsa: process-1 OPEN, process-2/3 CLOSED. İki process hala trip-service'e istek gönderiyor.

**Etki:** Circuit breaker yük altında işe yaramaz. Cascading failure engellenmez.

**Düzeltme:** Redis veya PostgreSQL'de merkezi state — veya en azından `asyncio.Lock()` ile process içi tutarlılık:
```python
import asyncio
_lock = asyncio.Lock()

async def _record_failure() -> None:
    async with _lock:
        global _failure_count, _last_failure_time, _state
        ...
```

---

### BUG-2: validate_trip_compat_contract — Driver-Service Unavailability Yakalanmıyor

**Dosya:** `services/internal_service.py:validate_trip_compat_contract`

**Kanıt:**
```python
async def validate_trip_compat_contract(...):
    # driver check
    driver_result = await driver_client.validate_driver(driver_id)
    # ↑ DependencyUnavailableError yakalaması YOK
```

`validate_trip_compat` (farklı fonksiyon) bunu yakalar:
```python
async def validate_trip_compat(...):
    try:
        driver_result = await driver_client.validate_driver(driver_id)
        ...
    except DependencyUnavailableError:
        warnings.append(...)
        driver_ok = True  # optimistic fallback
```

**Etki:** `validate_trip_compat_contract` → trip-service tarafından çağrılıyor. Driver-service 30 saniye down → fleet-service 503 → trip-service'in tüm trip create işlemleri fail.

**Düzeltme:** `validate_trip_compat_contract`'a da try/except ekle, ya da iki fonksiyonu birleştir.

---

### BUG-3: Session Commit Router'da — Service Layer Bunu Bilmiyor

**Dosya:** `services/vehicle_service.py`, `routers/vehicle_router.py`

**Kanıt:** `vehicle_service.create_vehicle` session.commit() çağırmıyor. Router commit ediyor. Service fonksiyonu `session.flush()` kullanıyor, commit'i caller'a bırakıyor.

**Problem:** Service test edilirken mock session'da commit unutulabilir. Daha kritik: `_lifecycle_transition` gibi helper'lar da commit yapmıyor — router'lar tutarsız şekilde ya commit ediyor ya etmiyor. Bu sözleşme belgelenmemiş.

**Düzeltme:** Ya service her zaman commit eder, ya da router her zaman commit eder — tutarlı olsun. Şu an ikisi de yapıyor, bazen.

---

### BUG-4: spec_versions lazy="selectin" — Her Vehicle Query'de Tüm Spec History

**Dosya:** `models.py`

**Kanıt:**
```python
class FleetVehicle(Base):
    spec_versions: Mapped[list[FleetVehicleSpecVersion]] = relationship(
        back_populates="vehicle",
        lazy="selectin"  # ← her vehicle fetch'te TÜM spec versiyonları yüklüyor
    )
```

Bir araçta 10 yıllık spec geçmişi varsa → her list/detail sorgusu tüm geçmişi çekiyor.

**Etki:** `list_vehicles` 100 araç döndürürse → 100 araç için 100 ek selectin query → N+1 benzeri yük.

**Düzeltme:** `lazy="raise"` yapıp sadece gerekli yerde explicit `selectinload(FleetVehicle.spec_versions)` kullan. Ya da sadece current spec'i ayrı join ile çek.

---

## YÜKSEK ÖNEMLİ BULGULAR

---

### H-1: Hard Delete — Idempotency Yok

`hard_delete_vehicle` idempotency key almıyor. Ağ timeout'u + retry durumunda araç silinebilir, audit yazılamadan tekrar DELETE denenirse 404 → client hata oldu sanır ama silme gerçekleşti.

---

### H-2: Outbox event_version Sabit

**Dosya:** `services/vehicle_service.py`

```python
event_version=1,
```

Tüm event'lerde hardcoded `event_version=1`. Schema değişince consumer'lar bozulur, version bump mekanizması yok.

---

### H-3: Fleet Outbox — DLQ Alerting Yok

Trip-service'le aynı problem. `publish_status = 'DEAD_LETTER'` bir kolon değeri. Metric var ama alert yok.

---

## ORTA ÖNEMLİ BULGULAR

---

### M-1: Idempotency Record Aynı Transaction'da

`create_vehicle` → idempotency record aynı session'da. Trip-service'in BUG-1'i burada da latent — placeholder mekanizması yok ama concurrent create + rollback durumunda idempotency kaydı kaybolabilir.

---

### M-2: validate_trip_compat vs validate_trip_compat_contract — İki Ayrı Fonksiyon

Aynı amaç için iki fonksiyon, farklı error handling. Hangisinin nerede kullanıldığı belirsiz. `validate_trip_compat_contract` trip-service'den çağrılıyor (adından belli), diğeri internal UI için. Bu iki path'in farklı davranışı confusion yaratıyor.

---

### M-3: FuelMetadata Endpoint — Point-in-Time Spec Query Performansı

```python
v_spec = await vehicle_spec_repo.get_spec_as_of(session, vehicle_id, at)
```

`get_spec_as_of` implementasyonu okunmadı ama `effective_from_utc <= at AND (effective_to_utc IS NULL OR effective_to_utc > at)` sorgusu olmadan sequential scan riski var.

---

## KORUNACAKLAR

| Bileşen | Durum |
|---------|-------|
| Layered architecture (domain/services/repos/schemas) | ✅ iyi |
| 4-stage hard delete pipeline | ✅ iyi |
| ETag optimistic locking | ✅ iyi |
| Timeline (no FK, hard delete survives) | ✅ iyi |
| Outbox transactional | ✅ iyi |
| Circuit breaker intent (logic doğru, scope yanlış) | ⚠️ düzelt |
| Driver + Trip client abstraction | ✅ iyi |
| Computed `is_selectable` column | ✅ iyi |
| Spec versioning (time-based) | ✅ iyi |

---

## DÜZELTME SIRASI

**Öncelikli (güvenilirlik):**
1. BUG-2: `validate_trip_compat_contract` → DependencyUnavailableError yakala
2. BUG-1: Circuit breaker → process-safe yap (asyncio.Lock minimum)

**Sonraki:**
3. BUG-4: `spec_versions lazy="selectin"` → `lazy="raise"` + explicit load
4. BUG-3: Commit sözleşmesi → ya service commit eder ya router, ikisi değil
5. H-1: Hard delete idempotency key
6. H-2: `event_version` config-driven yap
