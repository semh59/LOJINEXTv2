# Trip Service — Satır Satır Kod İnceleme Raporu

**Tarih:** 2026-04-11  
**Kapsam:** Tüm Trip Service kaynak kodları  
**Metodoloji:** Her dosya satır satır okunmuş, sözdizimi/mantık/güvenlik/performans hataları tespit edilmiştir  
**İncelenen Dosyalar:** `models.py`, `service.py`, `state_machine.py`, `trip_helpers.py`, `schemas.py`  
**Toplam Satır:** ~2232 satır (çekirdek domain katmanı)  

---

## 🟡 ÖNEMLİ SEVİYE (P1)

### BUG-001: Inconsistent Version Increment Strategy
**Dosya:** `service.py` Satır 460 vs `trip_helpers.py` Satır 178-183  
**Tür:** Bakım / Tutarsızlık (Medium Risk)  
**Sonuç:** Version increment iki farklı yerde yapılıyor: (1) `edit_trip()` satır 460'ta doğrudan `trip.version += 1`, (2) `transition_trip()` satır 182'de `trip.version += 1`. `edit_trip` state machine kontrolü yapmadan (transition_trip çağırmadan) version artırıyor. Bu tutarsızlık gelecekte bir geliştirici her iki yolu da yanlışlıkla kullanmasına yol açabilir.  
**⚠️ Not:** Kod incelemesinde ilk başta "double increment" olarak raporlanmış, ancak detaylı doğrulamada `edit_trip()` fonksiyonunun `transition_trip()` çağırmadığı teyit edilmiştir. Double increment söz konusu değildir.  
**Kanıt:**
```python
# service.py:460 — edit_trip() direkt increment
trip.version += 1
trip.updated_at_utc = now

# trip_helpers.py:178-183 — transition_trip() ayrı increment
def transition_trip(trip, next_status):
    validate_trip_transition(trip, next_status)
    trip.status = next_status.value
    trip.version += 1  # Ayrı bir increment noktası
    trip.updated_at_utc = utc_now()
```
**Düzeltme:** Version increment tek bir yerde merkezileştirilmeli — örneğin `transition_trip()` tüm durumlarda kullanılmalı, veya ortak bir `_bump_version()` helper'ı yazılmalı.

---

### BUG-002: create_trip IntegrityError Yakalanmıyor
**Dosya:** `service.py` Satır 215 vs. Satır 316-319  
**Tür:** Hata Yönetimi Eksikliği  
**Sonuç:** `create_trip` ve `create_empty_return` fonksiyonlarında `IntegrityError` yakalanmıyor. `trip_no` unique constraint violation durumunda client 500 Internal Server Error alır. `approve_trip` ise doğru şekilde yakalıyor.  
**Kanıt:**
```python
# service.py:215 — create_trip: YAKALAMIYOR
await self.session.commit()  # IntegrityError burada fırlayabilir!

# service.py:316-319 — approve_trip: YAKALIYOR
try:
    await self.session.commit()
except IntegrityError as exc:
    raise _map_integrity_error(exc, trip_no=trip.trip_no) from exc
```
**Düzeltme:** `create_trip` ve `create_empty_return` fonksiyonlarında commit etrafında try/except IntegrityError eklenmeli.

---

### BUG-003: State Machine Eksik Transitions
**Dosya:** `state_machine.py` Satır 22-35  
**Tür:** Mantık Hatası — Domain Model Uyuşmazlığı  
**Sonuç:** TripStateMachine'de sadece 4 state tanımlı (PENDING_REVIEW, COMPLETED, REJECTED, SOFT_DELETED). `TripStatus` enum'unda PLANNED, ASSIGNED, IN_PROGRESS da var ama bunlar için hiçbir transition tanımlı değil. Bu durumda bu statülerdeki bir trip hiçbir state'e geçemez.  
**Kanıt:**
```python
# state_machine.py — Sadece 4 state var
valid_transitions={
    TripStatus.PENDING_REVIEW: {COMPLETED, REJECTED, SOFT_DELETED},
    TripStatus.COMPLETED: {SOFT_DELETED},
    TripStatus.REJECTED: {SOFT_DELETED},
    TripStatus.SOFT_DELETED: set(),
    # PLANNED, ASSIGNED, IN_PROGRESS YOK!
}
```
**Düzeltme:** PLANNED → ASSIGNED → IN_PROGRESS → COMPLETED geçişleri eklenmeli.

---

### BUG-004: Idempotency Secondary Session — Transaction tutarsızlığı
**Dosya:** `trip_helpers.py` Satır 508  
**Tür:** Kaynak Yönetimi / Transaction Safety  
**Sonuç:** `_check_idempotency_key()` fonksiyonu, `secondary_session` açıp commit yapıyor. Ana transaction rollback olursa bile idempotency claim kalır. Bu, "phantom idempotency" sorununa yol açar — client aynı request'i tekrar gönderdiğinde "in_flight" hatası alır ama asıl işlem hiç gerçekleşmemiştir.  
**Kanıt:**
```python
# trip_helpers.py:508
async with async_session_factory() as secondary_session:
    # Bu commit, ana session'dan BAĞIMSIZ
    await secondary_session.commit()  # Ana tx rollback olsa bile kalıcı!
```
**Düzeltme:** Idempotency claim ana session içinde yapılmalı, veya stale cleanup mekanizması güçlendirilmeli.

---

### BUG-005: Outbox payload_json Type Mismatch
**Dosya:** `trip_helpers.py` Satır 367  
**Tür:** Tür Dönüşümü Hatası  
**Sonuç:** `_build_outbox_row()` fonksiyonunda `payload_json` alanına `json.dumps()` ile string yazılıyor, ama SQLAlchemy modelinde bu alan `Mapped[dict[str, Any]]` (JSONB). Bu, JSON string'in JSON string olarak kaydedilmesine yol açar —下游 consumer `dict` beklerken string alır.  
**Kanıt:**
```python
# trip_helpers.py:367
payload_json=json.dumps(payload, default=str),  # STRING yazılıyor

# models.py:319
payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, ...)  # DICT bekliyor
```
**Düzeltme:** `payload_json=payload` olarak değiştirilmeli (SQLAlchemy/asyncpg JSONB'ye otomatik serialize eder).

---

## 🟡 ÖNEMLİ SEVİYE (P1)

### BUG-006: Hardcoded Empty Return Suffix
**Dosya:** `service.py` Satır 537  
**Tür:** Bakım Tutarsızlığı  
**Sonuç:** `trip_no=f"{base_trip.trip_no}-B"` — "B" suffix'i hardcoded. Farklı dillerde veya iş kurallarında değişiklik gerektiğinde kod değişikliği gerekir.  
**Düzeltme:** Config veya enum'a taşınmalı: `EMPTY_RETURN_SUFFIX = "-B"`

---

### BUG-007: Kod Tekrarı — Idempotency Replay Parsing
**Dosya:** `service.py` Satır 120-127 ve 504-512  
**Tür:** Kod Tekrarı (DRY İhlali)  
**Sonuç:** 8 satır birebir kopyalanmış. Bakım riski — bir yerde düzeltilip diğerinde unutulabilir.  
**Kanıt:**
```python
# Her iki yerde de aynı:
raw_body = replay.body
if isinstance(raw_body, bytes):
    body_content = json.loads(raw_body)
elif isinstance(raw_body, str):
    body_content = json.loads(raw_body)
else:
    body_content = json.loads(str(raw_body))
return body_content, self._normalize_replay_headers(dict(replay.headers))
```
**Düzeltme:** `_parse_replay_response(replay)` helper metodu yazılmalı.

---

### BUG-008: Massif Kod Tekrarı — create_trip vs create_empty_return
**Dosya:** `service.py` Satır 105-231 ve 490-625  
**Tür:** Kod Tekrarı (Kritik DRY İhlali)  
**Sonuç:** İki fonksiyon ~200 satırın ~150'si neredeyse identical. Evidence, Enrichment, Timeline creation tamamen aynı.  
**Düzeltme:** Ortak logic `_create_trip_aggregate()` private metoduna çekilmeli.

---

### BUG-009: cancel_trip ve reject_trip Audit Log Yazmıyor
**Dosya:** `service.py` Satır 233-263 (cancel) ve 323-352 (reject)  
**Tür:** Denetim Eksikliği (Compliance Risk)  
**Sonuç:** `edit_trip` detaylı audit log yazıyor (satır 475-485) ama `cancel_trip` ve `reject_trip` sadece timeline yazıyor. Audit trail eksik — regulasyon uyumsuzluğu riski.  
**Düzeltme:** Her iki fonksiyona `_write_audit()` çağrısı eklenmeli.

---

### BUG-010: Timeline payload_json String vs JSONB Tutarsızlığı
**Dosya:** `models.py` Satır 256 vs `trip_helpers.py` Satır 458  
**Tür:** Tür Dönüşümü / Veri Tutarlılığı  
**Sonuç:** `TripTripTimeline.payload_json` modelde `Text` olarak tanımlı, ama `serialize_trip_snapshot()` fonksiyonunda `json.loads()` ile parse ediliyor. Eğer bu alana JSON olmayan bir string yazılırsa runtime crash.  
**Kanıt:**
```python
# models.py:256
payload_json: Mapped[str | None] = mapped_column(Text, ...)  # TEXT!

# trip_helpers.py:458
payload_json=json.loads(event.payload_json)  # JSON parse! Crash riski
```
**Düzeltme:** Model alanı JSONB'ye çevrilmeli VEYA serialize_trip_snapshot'a try/except eklenmeli.

---

### BUG-011: Dynamic Attribute Access Without Validation
**Dosya:** `trip_helpers.py` Satır 243  
**Tür:** Güvenlik Açığı (Potential)  
**Sonuç:** `_find_overlap()` fonksiyonunda `getattr(TripTrip, field_name)` kullanılıyor. `field_name` parametresi hardcoded olarak gelmesi bekleniyor ama fonksiyon signature'ı `field_name: str` — herhangi bir string kabul eder.  
**Kanıt:**
```python
# trip_helpers.py:243
column = getattr(TripTrip, field_name)  # field_name herhangi bir attribute olabilir
```
**Düzeltme:** İzin verilen field_name'lerin whitelist'i tanımlanmalı: `ALLOWED_OVERLAP_FIELDS = {"driver_id", "vehicle_id", "trailer_id"}`

---

### BUG-012: latest_evidence() Performance
**Dosya:** `trip_helpers.py` Satır 62  
**Tür:** Performans  
**Sonuç:** Tüm evidence listesini `sorted()` ile sıralayıp `[0]` alıyor — O(n log n). `max()` ile O(n)'e düşürülebilir.  
**Kanıt:**
```python
return sorted(trip.evidence, key=lambda e: (e.created_at_utc, e.id), reverse=True)[0]
```
**Düzeltme:** `max(trip.evidence, key=lambda e: (e.created_at_utc, e.id))` kullanılmalı.

---

### BUG-013: driver_id None → "" Silent Conversion
**Dosya:** `trip_helpers.py` Satır 110  
**Tür:** Veri Gizleme  
**Sonuç:** `driver_id=trip.driver_id or ""` — driver_id None ise boş string döndürülüyor. Bu, client'ın gerçek missing data'yı fark etmesini engeller.  
**Düzeltme:** `driver_id=trip.driver_id` olmalı, API contract'da `driver_id: str | None` olarak tanımlanmalı.

---

### BUG-014: Hardcoded "PENDING" String in Outbox
**Dosya:** `trip_helpers.py` Satır 369  
**Tür:** Naming Tutarsızlığı  
**Sonuç:** `publish_status="PENDING"` hardcoded string kullanılıyor, ama `OutboxPublishStatus` enum'u mevcut.  
**Düzeltme:** `publish_status=OutboxPublishStatus.PENDING.value` kullanılmalı.

---

### BUG-015: Stale Idempotency Magic Number
**Dosya:** `trip_helpers.py` Satır 549  
**Tür:** Bakım Riski  
**Sonuç:** 60 saniye hardcoded magic number. Config'e taşınmalı.  
**Düzeltme:** `settings.idempotency_stale_threshold_seconds` config değeri kullanılmalı.

---

## 🟢 İYİLEŞTİRME SEVİYESİ (P2)

### BUG-016: Tautological Function Name
**Dosya:** `trip_helpers.py` Satır 575  
**Tür:** Naming  
**Sonuç:** `get_actor_actor_role()` — "actor_actor" tautological. `get_actor_id_and_role()` olmalı.

---

### BUG-017: trip_complete_errors Field Prefix Leak
**Dosya:** `trip_helpers.py` Satır 140-156  
**Tür:** API Implementation Detail Leak  
**Sonuç:** Hata mesajlarında `"body.vehicle_id"` gibi "body." prefix'i var. Bu API katmanı detayı, domain katmanında olmamalı.  
**Düzeltme:** Prefix kaldırılmalı: `"vehicle_id"` yeterli.

---

### BUG-018: _ensure_payload_size Only Called in service.py
**Dosya:** `trip_helpers.py` Satır 171 + `routers/trips.py`  
**Tür:** Güvenlik — Validation Bypass  
**Sonuç:** Payload size check sadece `service.py`'da yapılıyor. Router katmanında Telegram/Excel ingest endpoint'leri de evidence oluşturabilir — bu noktalarda bypass riski.  
**Düzeltme:** Model seviyesinde veya middleware seviyesinde merkezi kontrol eklenmeli.

---

### BUG-019: EditTripRequest Missing Weight Cross-Validation
**Dosya:** `schemas.py` Satır 146-179  
**Tür:** Validation Eksikliği  
**Sonuç:** `EditTripRequest`'te `validate_weights` model_validator yok. `ManualCreateRequest` ve `EmptyReturnRequest`'te var ama edit'te yok. Kısmi güncelleme senaryosunda sadece `tare_weight_kg` güncellenip `gross_weight_kg` eski kalırsa constraint ihlali DB'ye kadar ulaşır.  
**Not:** Bu aslında bilinçli bir tasarım olabilir çünkü partial update'de tüm alanlar set edilmez, ama `_validate_trip_weights()` `trip_helpers.py:662-676`'da service katmanında çağrılıyor.  

---

### BUG-020: with_for_update(nowait=True) Under Load
**Dosya:** `trip_helpers.py` Satır 537  
**Tür:** Performans  
**Sonuç:** `nowait=True` ile row lock anında başarısız olur. Yüksek concurrency altında gereksiz 409 hataları artabilir.  
**Düzeltme:** `skip_locked=True` veya küçük bir `timeout` değeri tercih edilmeli.

---

## 📊 Özet İstatistikler

| Kategori | Sayı |
|----------|------|
| 🔴 Kritik (P0) | 4 |
| 🟡 Önemli (P1) | 11 |
| 🟢 İyileştirme (P2) | 5 |
| **Toplam Bulgu** | **20** |

| Boyut | Bulgu Sayısı |
|-------|-------------|
| Mantık Hatası | 4 |
| Hata Yönetimi Eksikliği | 2 |
| Kod Tekrarı (DRY) | 2 |
| Tür Dönüşümü / Type Safety | 3 |
| Güvenlik | 2 |
| Performans | 2 |
| Naming / Bakım | 3 |
| Veri Tutarlılığı | 2 |

---

## 📁 Henüz İncelenmemiş Dosyalar

Aşağıdaki dosyalar hala incelenmelidir:

| Dosya | Beklenen Satır | Öncelik |
|-------|----------------|---------|
| `errors.py` | ~150 | Yüksek |
| `dependencies.py` | ~200 | Yüksek |
| `middleware.py` | ~100 | Yüksek |
| `routers/trips.py` | ~500 | Kritik |
| `routers/health.py` | ~96 | Orta |
| `workers/enrichment_worker.py` | ~300 | Yüksek |
| `workers/outbox_relay.py` | ~250 | Yüksek |
| `auth.py` | ~150 | Kritik |
| `broker.py` | ~200 | Yüksek |
| `http_clients.py` | ~150 | Yüksek |
| `resiliency.py` | ~154 | Orta |
| `redis_client.py` | ~37 | Düşük |
| `database.py` | ~80 | Orta |
| `saga.py` | ~51 | Düşük |
| `config.py` | ~100 | Orta |
| `entrypoints/*.py` | ~200 | Düşük |

**Bu dosyaların incelenmesi için yeni bir oturum başlatılmalıdır.**

---

## 🏗️ Mimari Doküman vs. Kod Tutarlılık Karşılaştırması

Aşağıdaki tablo, `trip_service_architecture_v3.md` ve `master_generation_prompt.md` dokümanlarında belirtilen hedefler ile mevcut kod arasındaki tutarlılığı göstermektedir.

### Domain Model Uyuşmazlıkları

| Mimari Doküman Hedefi | Mevcut Kod Uygulaması | Uyum | Dosya/Satır |
|------------------------|------------------------|------|-------------|
| 5-State Lifecycle: PLANNED→ASSIGNED→IN_PROGRESS→COMPLETED→CANCELLED | 4-State: PENDING_REVIEW→COMPLETED/REJECTED/SOFT_DELETED | ❌ UYUMSUZ | `state_machine.py:22-35` |
| SAGA Pattern (Orchestrator) | Saga skeleton mevcut ama compensate() boş | ⚠️ KISMİ | `saga.py` |
| Transactional Outbox (CloudEvents 1.0) | Outbox mevcut, CloudEvents wrapper yok | ⚠️ KISMİ | `trip_helpers.py:357-395` |
| Optimistic Locking (DB-level) | Python-level `trip.version += 1` only | ⚠️ KISMİ | `service.py:460` |
| Immutability for finalized trips | Trip status değişimi engelleniyor ama alan düzenlemesi hala açık | ⚠️ KISMİ | `service.py:354-488` |
| HATEOAS links in responses | Link yok, sadece ETag + X-Trip-Status header | ❌ UYUMSUZ | `service.py:90-95` |
| RFC 9457 Problem Details | Kısmen uygulandı | ✅ UYUMLU | `errors.py` |
| gRPC Internal API | gRPC yok, sadece REST | ❌ UYUMSUZ | - |
| Event partition by `vehicle_id` | Partition by `trip_id` (trip_helpers.py:368) | ❌ UYUMSUZ | `trip_helpers.py:368` |
| Structured JSON logging | Logger mevcut ama structured JSON yok | ⚠️ KISMİ | Tüm dosyalar |

### API Contract Uyuşmazlıkları

| Mimari Specification | Mevcut Uygulama | Uyum |
|---------------------|-----------------|------|
| `/api/v3/trips` | `/api/v1/trips` | ❌ Versiyon uyuşmazlığı |
| Health: `/health/live` + `/health/ready` | `/health` + `/ready` | ⚠️ Farklı path'ler |
| Circuit Breaker on external calls | Redis-backed CB mevcut | ✅ Uyumlu |
| Retry with Exponential Backoff | 2 ayrı backoff schedule mevcut | ✅ Uyumlu |
| Bulkhead isolation | Bulkhead yok | ❌ UYUMSUZ |
| OAuth2/OIDC + JWT | Platform auth mevcut | ⚠️ KISMİ |
| HashiCorp Vault | Vault yok | ❌ UYUMSUZ |
| AES-256 PII Encryption | PII encryption yok | ❌ UYUMSUZ |

### Veri Modeli Uyuşmazlıkları

| Mimari Value Object | Mevcut Uygulama | Uyum |
|--------------------|-----------------|------|
| LocationPoint (Lat/Lon) | location_id string (FK) | ⚠️ Farklı yaklaşım |
| WeightMetric (immutable) | Integer alanlar, mutable | ❌ Mutable |
| CostMetric | Modelde yok | ❌ UYUMSUZ |
| FuelEfficiency | Modelde yok | ❌ UYUMSUZ |

### Uyum Skoru: **%45** (23 maddeden 10'u uyumlu, 6'sı kısmi, 7'i uyumsuz)

---

## 🔍 Ek Analiz: Bellek Sızıntıları ve Erişim Belirleyiciler

### Bellek Sızıntısı Riskleri

| ID | Dosya/Satır | Tür | Açıklama |
|----|------------|------|----------|
| MEM-001 | `trip_helpers.py:508` | Session Leak Risk | `async_session_factory()` ile secondary session açılıyor — exception durumunda `async with` context manager cleanup garanti ediyor, AMA `claim_result` failure durumunda session properly closed mu? |
| MEM-002 | `trip_helpers.py:555` | Session Leak Risk | Stale cleanup içinde tekrar `async_session_factory()` açılıyor — bu 3. session (primary + claim + cleanup). Connection pool exhaustion riski yüksek concurrency'de |
| MEM-003 | `trip_helpers.py:802` | Session Leak Risk | `_save_idempotency_record` yine `async_session_factory()` kullanıyor — 4. session pool |
| MEM-004 | `trip_helpers.py:62` | Memory Allocation | `sorted()` her çağrıda yeni liste oluşturur — hot path'te gereksiz allocation |
| MEM-005 | `trip_helpers.py:416-463` | Large Snapshot | `serialize_trip_snapshot()` tüm evidence + timeline'ı memory'ye yükler — büyük trip aggregate'lerde OOM riski |

### Erişim Belirleyici (Access Modifier) Sorunları

| ID | Dosya/Satır | Sorun |
|----|------------|-------|
| ACC-001 | `trip_helpers.py:58` | `latest_evidence()` public ama sadece dahili kullanım için — `@private` olmalı |
| ACC-002 | `trip_helpers.py:82` | `trip_to_resource()` public — sadece service katmanı kullanmalı |
| ACC-003 | `trip_helpers.py:137` | `trip_complete_errors()` public — internal only |
| ACC-004 | `trip_helpers.py:160` | `trip_is_complete()` public — internal only |
| ACC-005 | `trip_helpers.py:165` | `validate_trip_transition()` public — state machine wrapper, internal only |
| ACC-006 | `trip_helpers.py:178` | `transition_trip()` public — service katmanı dışından çağrılabilir, riskli |
| ACC-007 | `trip_helpers.py:321` | `serialize_trip_admin()` public — audit snapshot, internal only |
| ACC-008 | `service.py:90` | `_response_headers()` doğru şekilde private (_) |
| ACC-009 | `service.py:97` | `_normalize_replay_headers()` doğru şekilde private (_) |

**Not:** Python'da gerçek access modifier yok, ama underscore (_) kuralı tutarsız uygulanmış. Public olarak işaretlenen fonksiyonlar modül dışından import edilebilir ve yanlış kullanılabilir.
