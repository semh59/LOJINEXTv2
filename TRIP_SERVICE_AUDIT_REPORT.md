# TRIP SERVICE — DETAYLI AUDIT RAPORU
## Satır Satır İnceleme ve Bug Düzeltmeleri

**Tarih:** 9 Nisan 2026  
**Kapsam:** `services/trip-service/src/trip_service/` altındaki tüm modüller

---

## 1. MİMARİ GENEL BAKIŞ

### Modül Bağımlılık Haritası
```
main.py → routers/trips.py → service.py → trip_helpers.py
                          ↘ dependencies.py → resiliency.py
                                             → http_clients.py
                                             → auth.py
models.py ← (tüm modüller)
schemas.py ← routers/trips.py, service.py, trip_helpers.py
errors.py ← (tüm modüller)
state_machine.py ← trip_helpers.py
```

### Katman Yapısı
| Katman | Dosyalar | Sorumluluk |
|--------|----------|------------|
| **API Gateway** | `main.py`, `middleware.py` | FastAPI app, CORS, error handling |
| **Routers** | `routers/trips.py`, `routers/health.py`, `routers/driver_statement.py`, `routers/removed_endpoints.py` | HTTP endpoint tanımları |
| **Service Layer** | `service.py` (TripService class, 584 satır) | İş mantığı koordinasyonu |
| **Helpers** | `trip_helpers.py` (~780 satır) | Paylaşılan domain yardımcıları |
| **Dependencies** | `dependencies.py` (~340 satır) | External service çağrıları (Fleet, Location) |
| **Data** | `models.py` (362 satır) | SQLAlchemy ORM modelleri (9 tablo) |
| **Contracts** | `schemas.py` | Pydantic request/response modelleri |
| **Workers** | `workers/enrichment_worker.py`, `workers/outbox_relay.py` | Background processing |
| **Infrastructure** | `resiliency.py`, `auth.py`, `config.py`, `database.py`, `broker.py`, `http_clients.py` | Cross-cutting concerns |

---

## 2. MODELS.PY ANALİZİ (362 satır, 9 Tablo)

### Tablolar
1. **`trip_trips`** — Ana trip aggregate (26 kolon, 6 FK, 13 index/constraint)
2. **`trip_trip_evidence`** — Kaynak kanıt verileri (14 kolon, 4 index)
3. **`trip_trip_enrichment`** — Enrichment durumu ve worker claim (12 kolon, 3 index)
4. **`trip_trip_timeline`** — Immutable timeline olayları (7 kolon, 2 index)
5. **`trip_trip_delete_audit`** — Hard delete audit snapshot (8 kolon, 2 index)
6. **`trip_audit_log`** — Genel high-fidelity audit (10 kolon, 1 index)
7. **`trip_outbox`** — Transactional outbox (16 kolon, 5 index)
8. **`trip_idempotency_records`** — Idempotency kayıtları (7 kolon, 1 index)
9. **`worker_heartbeats`** — Worker sağlık kontrolü (2 kolon)

### Kritik Constraints
- `ck_trips_completed_complete` — COMPLETED trip'ler tüm route alanlarını doldurmak zorunda
- `ck_trips_gross_gte_tare` — gross >= tare kontrolü
- `ck_trips_net_eq_diff` — net = gross - tare kontrolü
- `ck_trips_strict_sources_complete` — ADMIN_MANUAL, EMPTY_RETURN, EXCEL_IMPORT kaynakları completeness zorunlu
- `ck_trips_imported_source_reference_key` — TELEGRAM/EXCEL için source_reference_key zorunlu

### Gözlemler
- ✅ ULID (26 karakter) primary key kullanımı tutarlı
- ✅ `passive_deletes=True` cascade yapılandırması doğru
- ✅ Composite index'ler overlap sorguları için optimize
- ✅ JSONB kolonları raw_payload ve snapshot için uygun
- ⚠️ `TripTripEvidence.raw_payload_json` hem `dict` hem `str` tipinde (`Mapped[dict | str]`) — tutarsız kullanım

---

## 3. SERVICE.PY ANALİZİ (584 satır)

### TripService Class Metodları
| Metot | Satır | İşlev |
|-------|-------|-------|
| `create_trip()` | 96-213 | Manuel trip oluşturma |
| `cancel_trip()` | 215-245 | Soft-delete |
| `approve_trip()` | 247-303 | PENDING_REVIEW → COMPLETED |
| `reject_trip()` | 305-334 | PENDING_REVIEW → REJECTED |
| `edit_trip()` | 336-456 | Trip alan güncelleme |
| `create_empty_return()` | 458-584 | Boş dönüş trip'i |

### Tasarım Özellikleri
- ✅ Her metot `tuple[dict, dict]` döndürür (resource + headers)
- ✅ ETag/If-Match optimistic concurrency control
- ✅ Idempotency key desteği (canonical + legacy header)
- ✅ Overlap check (driver, vehicle, trailer için advisory lock)
- ✅ Audit log yazma
- ✅ Outbox event gönderimi
- ✅ Prometheus metrik artırımı

### Bulunan Sorunlar
1. **`_response_headers()` tutarsızlık** (satır 91-93):
   - `service.py`: `ETag: "{version}"` formatı kullanıyor
   - `trips.py`: `make_etag(trip.id, trip.version)` kullanıyor
   - ⚠️ **FARKLI ETag formatları** — client confusion riski

2. **`now = datetime.now(UTC)` vs `utc_now()` tutarsızlığı** (satır 122, 226, 283, 318, 373, 494):
   - `trip_helpers.py` tutarlı şekilde `utc_now()` kullanıyor
   - `service.py` doğrudan `datetime.now(UTC)` kullanıyor
   - ⚠️ Bakım riski — tek noktadan değişim zor

3. **`cancel_trip()` overlap check yok** (satır 215-245):
   - Soft-delete yaparken overlap kontrolü yok (kasıtlı olabilir)

---

## 4. TRIP_HELPERS.PY ANALİZİ (~780 satır, 41 fonksiyon)

### Fonksiyon Kategorileri
| Kategori | Fonksiyonlar | Sayı |
|----------|-------------|------|
| Trip Serialization | `trip_to_resource`, `serialize_trip_admin`, `serialize_trip_snapshot` | 3 |
| Status Management | `normalize_trip_status`, `is_deleted_trip_status`, `transition_trip`, `validate_trip_transition` | 4 |
| Completeness | `trip_complete_errors`, `trip_is_complete`, `_ensure_complete_for_completion` | 3 |
| Route Context | `apply_trip_context`, `calculate_planned_end` | 2 |
| Overlap Detection | `assert_no_trip_overlap`, `_find_overlap`, `_acquire_overlap_locks`, `_advisory_lock_key` | 4 |
| Audit | `_write_audit`, `_write_outbox`, `_create_outbox_event`, `_build_outbox_row` | 4 |
| Idempotency | `_check_idempotency_key`, `_save_idempotency_response`, `_save_idempotency_record`, `_resolve_idempotency_key` | 4 |
| Outbox | `_event_payload`, `_write_outbox` | 2 |
| Utility | `_generate_id`, `_coerce_actor_type`, `_merged_payload_hash`, `_validate_trip_weights`, `_compute_data_quality_flag`, `_set_enrichment_state`, `_ensure_payload_size`, `utc_now`, `_get_trip_or_404`, `_constraint_name`, `_map_integrity_error` | 11 |
| Business Rules | `_maybe_require_change_reason`, `_classify_manual_status` | 2 |
| Auth | `get_actor_actor_role` | 1 |
| Evidence | `latest_evidence` | 1 |
| Delete | `build_delete_audit` | 1 |

### DÜZELTİLEN BUG'LAR

#### BUG-1: Dead Code (KRİTİK)
**Konum:** `_event_payload()` sonrası, eski satır ~680  
**Sorun:** `return TripStatus.COMPLETED, None` — erişilemez kod, fonksiyonun return'ünden sonra  
**Etki:** Syntax hatası yok ama kod kalitesi ve confusions riski  
**Düzeltme:** Satır kaldırıldı ✅

#### BUG-2: `_maybe_require_change_reason()` Mantık Hatası (KRİTİK)
**Konum:** trip_helpers.py  
**Sorun:** 
- `driver_change_requires_reason` import ediyordu — `errors.py`'de bu fonksiyon yok!
- `auth.is_super_admin` kontrolü eksikti
- ADMIN kullanıcılar imported trip'lerde driver değiştirebiliyordu
**Etki:** Runtime `ImportError` veya yetkilendirme bypass  
**Düzeltme:** trips.py'deki doğru implementasyon kullanıldı ✅

#### BUG-3: Idempotency Recursive Guard (ORTA)
**Konum:** `_check_idempotency_key()`  
**Sorun:** Stale placeholder temizlendikten sonra recursive call'da depth limit yok  
**Etki:** Teorik sonsuz recursion riski  
**Düzeltme:** `_depth` parametresi eklendi, `_depth >= 2` hard limit ✅

#### BUG-4: Circular Import (KRİTİK)
**Konum:** `dependencies.py` → `service.py` → `dependencies.py`  
**Sorun:** `get_trip_service()` top-level `from trip_service.service import TripService` yapıyordu  
**Etki:** Module import sırasında `ImportError`  
**Düzeltme:** Lazy import (fonksiyon gövdesinde import) ✅

#### BUG-5: Eksik Fonksiyonlar (KRİTİK)
**Konum:** trip_helpers.py  
**Sorun:** `service.py` bu fonksiyonları import ediyordu ama trip_helpers.py'de tanımlı değillerdi:
- `_generate_id()` — ULID primary key üretimi
- `_coerce_actor_type()` — Role string normalizasyonu
- `_resolve_idempotency_key()` — Canonical/legacy header çözümleme
- `_save_idempotency_record()` — Idempotency response persistance
**Etki:** `ImportError: cannot import name '_coerce_actor_type'`  
**Düzeltme:** 4 fonksiyon trip_helpers.py'ye eklendi ✅

#### BUG-6: `_set_enrichment_state` Tutarlılık (DÜŞÜK)
**Konum:** trip_helpers.py, `_set_enrichment_state()` son satırı  
**Sorun:** `datetime.now(UTC)` kullanıyordu, modülün `utc_now()` helper'ı yerine  
**Etki:** Tutarlılık sorunu, test edilebilirlik riski  
**Düzeltme:** `utc_now()` kullanıldı ✅

---

## 5. ROUTERS/TRIPS.PY ANALİZİ (1135 satır)

### Endpoint'ler
| Method | Path | Satır | İşlev |
|--------|------|-------|-------|
| GET | `/internal/v1/trips/driver-check/{driver_id}` | 414 | Driver referans kontrolü |
| POST | `/internal/v1/assets/reference-check` | 430 | Asset referans kontrolü |
| POST | `/internal/v1/trips/slips/ingest` | 441 | Telegram slip ingest |
| POST | `/internal/v1/trips/slips/ingest-fallback` | 591 | Fallback Telegram ingest |
| POST | `/internal/v1/trips/excel/ingest` | 707 | Excel ingest |
| GET | `/internal/v1/trips/excel/export-feed` | 829 | Excel export feed |
| POST | `/api/v1/trips` | 881 | Manuel trip oluşturma |
| GET | `/api/v1/trips` | 902 | Trip listesi |
| GET | `/api/v1/trips/{trip_id}` | 961 | Trip detay |
| GET | `/api/v1/trips/{trip_id}/timeline` | 974 | Trip timeline |
| PATCH | `/api/v1/trips/{trip_id}` | 986 | Trip düzenleme |
| POST | `/api/v1/trips/{trip_id}/cancel` | ~1005 | Trip iptal |
| POST | `/api/v1/trips/{trip_id}/approve` | ~1030 | Trip onay |
| POST | `/api/v1/trips/{trip_id}/reject` | ~1055 | Trip red |
| POST | `/api/v1/trips/{trip_id}/empty-return` | ~1075 | Boş dönüş |
| POST | `/internal/v1/trips/{trip_id}/hard-delete` | ~1095 | Hard delete |
| POST | `/internal/v1/trips/{trip_id}/enrichment/retry` | ~1115 | Enrichment retry |
| GET | `/internal/v1/trips/{trip_id}/enrichment/status` | ~1125 | Enrichment durum |

### Gözlemler
- ✅ Endpoint tasarımı RESTful ve tutarlı
- ✅ Her endpoint proper auth dependency kullanıyor
- ⚠️ **Duplicate fonksiyon sorunu:** `_generate_id`, `_coerce_actor_type`, `_resolve_idempotency_key`, `_save_idempotency_record`, `_validate_trip_weights`, `_compute_data_quality_flag`, `_constraint_name`, `_map_integrity_error`, `_set_enrichment_state`, `_maybe_require_change_reason` hem trips.py hem trip_helpers.py'de tanımlı
- ⚠️ **Büyük dosya (1135 satır)** — router seviyesinde iş mantığı çok yoğun

---

## 6. DEPENDENCIES.PY ANALİZİ (~340 satır)

### External Service Bağımlılıkları
| Servis | Fonksiyonlar | Circuit Breaker |
|--------|-------------|----------------|
| Fleet Service | `validate_trip_references()`, `probe_fleet_service()` | `fleet_breaker` |
| Location Service | `resolve_route_by_names()`, `fetch_trip_context()`, `probe_location_service()` | `location_breaker` |

### Özellikler
- ✅ Tenacity retry (3 attempt, exponential backoff)
- ✅ Circuit breaker (5 failure threshold, 30s recovery)
- ✅ Internal service token (JWT audience-based)
- ✅ Correlation ID propagation
- ✅ Legacy field compatibility (`_resolve_trip_compat_flag`)
- ✅ Proper error mapping (404, 409, 422 → domain errors)

---

## 7. RESILIENCY.PY ANALİZİ (87 satır)

### Circuit Breaker Implementasyonu
- **State Machine:** CLOSED → OPEN → HALF_OPEN → CLOSED
- **Threshold:** 5 consecutive failures
- **Recovery:** 30 saniye timeout
- **Scope:** In-memory (process-local)
- ⚠️ **Dağıtım riski:** Multi-process/multi-pod ortamında breaker state paylaşılmaz
- ✅ Decorator pattern ile temiz kullanım

---

## 8. ERRORS.PY ANALİZİ (327 satır)

### Problem Detail Format (RFC 9457)
- ✅ Tutarlı `ProblemDetailError` base class
- ✅ Structured error response: `type`, `title`, `status`, `detail`, `instance`, `code`, `request_id`
- ✅ 25+ domain-specific error fabrika fonksiyonu
- ✅ `validation_exception_handler` FastAPI integration

### Error Kodları
| HTTP | Kod | Sayı |
|------|-----|------|
| 401 | `TRIP_AUTH_REQUIRED`, `TRIP_AUTH_INVALID` | 2 |
| 403 | `TRIP_FORBIDDEN` | 1 |
| 404 | `TRIP_NOT_FOUND`, `TRIP_ENDPOINT_REMOVED` | 2 |
| 409 | `TRIP_TRIP_NO_CONFLICT`, `TRIP_SOURCE_REFERENCE_CONFLICT`, vs. | 12 |
| 412 | `TRIP_VERSION_MISMATCH` | 1 |
| 422 | `TRIP_VALIDATION_ERROR`, `TRIP_CHANGE_REASON_REQUIRED`, vs. | 5 |
| 428 | `TRIP_IF_MATCH_REQUIRED` | 1 |
| 500 | `TRIP_INTERNAL_ERROR` | 1 |
| 503 | `TRIP_DEPENDENCY_UNAVAILABLE` | 1 |

---

## 9. DÜZELTİLEN DOSYALAR ÖZETİ

| Dosya | Değişiklik | Bug |
|-------|-----------|-----|
| `trip_helpers.py` | Dead code kaldırıldı | BUG-1 |
| `trip_helpers.py` | `_maybe_require_change_reason` düzeltildi | BUG-2 |
| `trip_helpers.py` | `_check_idempotency_key` recursive guard | BUG-3 |
| `trip_helpers.py` | 4 eksik fonksiyon eklendi | BUG-5 |
| `trip_helpers.py` | `_set_enrichment_state` utc_now() | BUG-6 |
| `dependencies.py` | Lazy import circular fix | BUG-4 |

---

## 10. KALAN RİSKLER VE ÖNERİLER

### YÜKSEK RİSK
1. **ETag Format Tutarsızlığı:** `service.py` (`"{version}"`) vs `trips.py` (`make_etag(id, version)`) — client'lar farklı formatlar görecek
2. **Duplicate Fonksiyonlar:** trips.py'deki local fonksiyonlar trip_helpers.py ile çakışıyor — birisi değişirse sessiz divergence

### ORTA RİSK
3. **`datetime.now(UTC)` vs `utc_now()` Tutarsızlığı:** service.py her yerde `datetime.now(UTC)` kullanıyor, trip_helpers.py `utc_now()` kullanıyor
4. **In-Memory Circuit Breaker:** Multi-process ortamında state paylaşılmıyor
5. **TripTripEvidence.raw_payload_json:** `Mapped[dict | str]` tip tutarsızlığı

### DÜŞÜK RİSK
6. **Büyük Dosya Boyutu:** trips.py (1135 satır), trip_helpers.py (~780 satır), service.py (584 satır) — refactoring önerisi
7. **`_save_idempotency_response` vs `_save_idempotency_record`:** İki benzer ama farklı fonksiyon — confusion riski

---

## SONUÇ

Trip Service, mimari olarak sağlam bir microservice tasarımına sahip: Transactional outbox pattern, idempotency, circuit breaker, optimistic concurrency, audit trail ve overlap detection gibi enterprise pattern'ler doğru uygulanmış. 

Bulunan 6 bug'ın tümü düzeltilmiştir. En kritik olanlar circular import (BUG-4) ve eksik fonksiyonlar (BUG-5) idi — bunlar servisin hiç başlamamasına neden olabilirdi.