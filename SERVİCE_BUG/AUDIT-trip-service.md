# AUDIT: trip-service
**Tarih:** 2025  
**Kapsam:** Tüm src/ dosyaları kanıt temelli incelendi  
**Yargı:** Production'a giremez — 3 kritik veri bozulma riski aktif

---

## MİMARİ YAPI

```
trip_service/
  routers/trips.py       ← 1596 satır GOD ROUTER
  trip_helpers.py        ← 611 satır fonksiyon dumpı
  state_machine.py       ← mevcut ama eksik
  workers/               ← outbox + enrichment
  schemas.py             ← iyi
  models.py              ← iyi
```

**Eksik katmanlar:**
- `services/` — yok → tüm iş mantığı router'da
- `repositories/` — yok → SQL her yerde dağınık

---

## KRİTİK BULGULAR (veri bozuyor)

---

### BUG-1: Idempotency Race — Duplicate Trip

**Dosya:** `trip_helpers.py:_check_idempotency_key` + `routers/trips.py`

**Kanıt:**
```python
# _check_idempotency_key — aynı session üzerinden çalışıyor
claim_stmt = pg_insert(TripIdempotencyRecord).values(
    response_status=0,  # placeholder
    ...
).on_conflict_do_nothing(...)
claim_result = await session.execute(claim_stmt)
# ...
await session.flush()
# ... asıl iş yapılıyor ...
await session.commit()  # ← placeholder + trip birlikte commit
```

**Senaryo:**
1. Request A → placeholder insert (rowcount=1) → devam eder
2. Request A → IntegrityError (trip_no unique constraint) → `session.rollback()`
3. Rollback **placeholder'ı da siler** (aynı transaction)
4. Request A retry gelir → placeholder yok → `rowcount=1` → tekrar işlenir
5. **Duplicate trip**

**Etki:** Her IntegrityError sonrası retry → duplicate kayıt.

---

### BUG-2: State Machine Bypass — cancel_trip

**Dosya:** `routers/trips.py:cancel_trip`

**Kanıt:**
```python
# state_machine.py
TripStatus.COMPLETED: set(),   # terminal — geçiş yok
TripStatus.REJECTED: set(),    # terminal — geçiş yok

# routers/trips.py — cancel_trip
trip.status = TripStatus.SOFT_DELETED.value  # ← transition_trip() çağrılmıyor
trip.version += 1
```

**Etki:**
- COMPLETED trip silinebilir → downstream'e `trip.completed.v1` + `trip.soft_deleted.v1` aynı trip için → consumer tutarsız state
- REJECTED trip silinebilir → state machine bunu engelleyemiyor

---

### BUG-3: Overlap Check Atlanıyor

**Dosya:** `routers/trips.py:edit_trip`

**Kanıt:**
```python
# edit_trip
if overlap_fields & set(changed_fields) and trip.planned_end_utc is not None:
    await assert_no_trip_overlap(...)
# ↑ planned_end_utc=None ise overlap check ÇALIŞMIYOR
```

**Etki:** Fallback trip'ler (`TG-FALLBACK-*`) `planned_end_utc=None` ile oluşuyor. Bu trip'lere sürücü/araç ataması yapılırken overlap check atlanır → aynı araç/sürücüye aynı anda iki aktif trip.

---

## YÜKSEK ÖNEMLİ BULGULAR (güvenilirlik riski)

---

### H-1: HTTP Retry Yok — Fleet/Location Çağrıları

**Dosya:** `dependencies.py`, `http_clients.py`

**Kanıt:**
```python
def _build_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=settings.dependency_timeout_seconds,
        # retry yok
    )
```

`ensure_trip_references_valid` ve `fetch_trip_context` → tek deneme, 500 alırsa direkt fail.

**Etki:** Fleet/location servisinin 30 saniyelik restart'ı → bu window'daki tüm trip create/edit istekleri 503.

---

### H-2: Circuit Breaker Yok

**Dosya:** `dependencies.py`, `http_clients.py`

Fleet-service veya location-service down → tüm trip yazma işlemleri fail. Cascade failure engellemiyor. Degrade mod yok.

---

### H-3: Enrichment Claim TTL vs HTTP Timeout

**Dosya:** `workers/enrichment_worker.py`, `config.py`

`enrichment_claim_ttl_seconds` ile `dependency_timeout_seconds` arasında config seviyesi kontrol yok. Eğer `dependency_timeout >= claim_ttl` → worker A beklerken claim expire → worker B aynı row'u claim eder → çift enrichment.

---

### H-4: Outbox Ordering Garantisiz

**Dosya:** `workers/outbox_relay.py`

Multi-worker deployment'ta `FOR UPDATE SKIP LOCKED` farklı worker'lara farklı row'lar verir. Aynı trip'in `trip.created.v1` ve `trip.completed.v1` event'leri farklı worker'a düşebilir → ikincisi önce publish olabilir.

**Etki:** Consumer `trip.completed.v1` alır ama `trip.created.v1` henüz gelmemiş → `trip_id` bilinmiyor → 404.

---

### H-5: DLQ Görünmez

`publish_status = 'DEAD_LETTER'` bir kolon değeri. Alert yok, webhook opsiyonel, monitoring yok. Critical event (örn. `trip.completed.v1`) DEAD_LETTER'a düşse kimse haberdar olmaz.

---

### H-6: Event Payload Thin

**Dosya:** `trip_helpers.py:_event_payload`

```python
return {
    "trip_id": trip.id,
    "trip_no": trip.trip_no,
    "status": normalize_trip_status(trip.status),
    "version": trip.version,
    "updated_at_utc": ...,
}
```

5 field. Consumer downstream için driver_id, vehicle_id, route bilgisi yok → her event için GET /trips/{id} çağrısı → fan-out yükü trip-service'e döner.

---

## ORTA ÖNEMLİ BULGULAR

---

### M-1: Service Layer Yok

1596-satır `trips.py` = controller + service + repository. 4 ayrı create endpoint (telegram, fallback, excel, manual) aynı TripTrip inşaat mantığını tekrar ediyor. Bir kural değiştiğinde 4 yerde değiştirilmesi gerekiyor — biri unutulur.

---

### M-2: Repository Layer Yok

SQL sorguları router ve helper arasında dağınık. `_REFERENCE_EXCLUDED_STATUSES` hem `trip_helpers.py` hem `trips.py`'de tanımlı — duplicate, senkronizasyon riski.

---

### M-3: Row-Level Isolation Yok

`list_trips`, `get_trip`, `get_trip_timeline`:
```python
del auth  # auth check yapılıyor ama kullanılmıyor
```

OPERATOR rolündeki kullanıcı tüm sürücülerin tüm trip'lerini görebilir.

---

### M-4: approve_trip Transaction Eksik

**Dosya:** `routers/trips.py:approve_trip`

```python
transition_trip(trip, TripStatus.COMPLETED)
# ...
await _create_outbox_event(session, trip, "trip.completed.v1")
TRIP_COMPLETED_TOTAL.inc()
await session.commit()  # ← try/except yok
```

`inactivate_driver` benzeri — commit IntegrityError'ı yakalamazsa raw 500 dönüyor.

---

## KORUNACAKLAR (dokunma)

| Bileşen | Durum |
|---------|-------|
| Broker abstraction (MessageBroker ABC) | ✅ iyi |
| Advisory lock overlap detection | ✅ iyi |
| ETag + version optimistic locking | ✅ iyi |
| Outbox pattern (transactional) | ✅ iyi |
| Enrichment worker claim (FOR UPDATE SKIP LOCKED) | ✅ iyi |
| Auth layer (JWT/JWKS, service token) | ✅ iyi |
| Pydantic v2 schemas | ✅ iyi |
| Enrichment backoff (1m→5m→15m→60m→6h) | ✅ iyi |
| ULID primary keys | ✅ iyi |

---

## DÜZELTME SIRASI

**Sprint 1 — Veri bozulması (şimdi):**
1. BUG-1: Idempotency placeholder'ı ayrı transaction'a taşı
2. BUG-2: `cancel_trip` → `transition_trip()` kullan, state machine'e SOFT_DELETED geçişleri ekle
3. BUG-3: `planned_end_utc=None` → `effective_end = planned_end or (trip_start + 24h)` kullan

**Sprint 2 — Güvenilirlik:**
4. H-1: `tenacity` ile HTTP retry (3 deneme, exponential backoff)
5. H-2: Circuit breaker (fleet + location)
6. H-3: Config validator — `dependency_timeout < claim_ttl * 0.6`

**Sprint 3 — Maintainability:**
7. M-1/M-2: Service layer + Repository layer extraction

**Sprint 4 — Observability:**
8. H-4: Outbox partition-key bazlı ordering
9. H-5: DLQ alerting (webhook / critical log tag)
10. H-6: Event payload genişlet (driver_id, vehicle_id, route_id ekle)
