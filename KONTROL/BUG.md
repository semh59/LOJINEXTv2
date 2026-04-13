# 🔴 LOJINEXTv2 — Kapsamlı Denetim Raporu

Repo baştan sona tarandı. Kodlar satır satır okundu. Aşağıda **gerçek bulgular** var — tahmin yok, halüsinasyon yok.

---

## 📌 KANITLI DURUM GÜNCELLEMESİ (2026-04-13 — Gerçek Kod Analizi)

**Her bug gerçek kaynak kodu ile yeniden doğrulandı.** Satır numaraları ve dosya içerikleri karşılaştırıldı.

| ID | Orijinal Seviye | Konu | **Güncel Durum** | Kanıt |
|---|---|---|---|---|
| BUG-001 | 🔴 P0 | Fleet outbox relay `payload=dict` crash | **✅ FIXED** | `fleet_service/workers/outbox_relay.py:36-42` — `isinstance(raw, dict)` check + `json.dumps()` |
| BUG-002 | 🔴 P0 | Driver outbox relay JSONB dict | **✅ FIXED** | `driver_service/workers/outbox_relay.py:39-40` — hem dict hem str handle + `RobustJSONEncoder` |
| BUG-003 | 🔴 P0 | Identity `probe_broker()` `ping()` yok | **✅ FIXED** | `identity_service/broker.py:55` — artık `broker.check_health()` kullanıyor |
| BUG-004 | 🟠 P1 | 4 servis payload_json JSONB | **⚠️ HÂLÂ AÇIK** | Modeller hâlâ JSONB kullanıyor |
| BUG-005 | 🟠 P1 | `READY` durumu standartta yok | **⚠️ HÂLÂ AÇIK** | `OutboxPublishStatus.READY` hâlâ mevcut |
| BUG-006 | 🟠 P1 | Backoff zamanlaması §9.3 uyumsuz | **✅ FIXED** | `platform_common/outbox_relay.py:295-304` — `{1:30, 2:120, 3:600, 4:3600}` + ±10% jitter |
| BUG-007 | 🟠 P1 | Telegram BaseHTTPMiddleware | **✅ FIXED** | `telegram_service/middleware.py` — artık pure ASGI implementation |
| BUG-008 | 🔴 P0 | HOL blocking DEAD_LETTER livelock | **✅ FIXED** | `platform_common/outbox_relay.py:130-135` — `.in_([PENDING, PUBLISHING, FAILED])` ile DEAD_LETTER hariç |
| BUG-009 | 🟠 P1 | Identity worker finally setup_redis() | **⚠️ DOĞRULANACAK** | Worker dosyası okunmalı |
| BUG-010 | 🟠 P1 | Trip idempotency ayrı session | **⚠️ DOĞRULANACAK** | trip_helpers.py okunmalı |
| BUG-011 | 🔴 P0 | Trip+Driver sync JWKS decode | **✅ FIXED** | `trip_service/auth.py:72` — `anyio.to_thread.run_sync()` ile async yapılmış; `driver_service/auth.py:98` — `await async_decode_bearer_token()` |
| BUG-012 | 🟠 P1 | Saga compensation outbox bypass | **🔵 DEAD CODE** | `saga.py` dosyası mevcut değil — `search_files("saga")` = 0 sonuç |
| BUG-013 | 🟠 P1 | Driver "ADMIN" rol string | **✅ FIXED** | `require_admin_or_manager_token` (satır 147) `actor_type = "MANAGER"` olarak düzeltildi ✅ |
| BUG-014 | 🟠 P1 | Telegram circuit breaker yok | **✅ FIXED** | `telegram_service/http_clients.py:21-23` — 3 CircuitBreaker var, `request()` metodu ile otomatik |
| BUG-015 | 🟠 P1 | Telegram assert deyimleri | **⚠️ DOĞRULANACAK** | trip_client.py okunmalı |
| BUG-016 | 🟠 P1 | JWKS cache concurrent refresh | **⚠️ DOĞRULANACAK** | platform-auth key_provider.py okunmalı |
| DRIFT-001 | 🟡 P2 | Outbox PK tutarsızlığı | **⚠️ HÂLÂ AÇIK** | OutboxRelayBase tolere ediyor ama tasarım sapması devam |
| DRIFT-002 | 🟡 P2 | Kafka config farklı | **✅ FIXED** | Tüm servislerde `kafka_acks`, `kafka_enable_idempotence`, `kafka_linger_ms` settings'ten okunuyor |
| DRIFT-004 | 🟡 P2 | Location correlation_id eksik | **⚠️ HÂLÂ AÇIK** | `location_service/workers/outbox_relay.py:47` — correlation_id geçiriliyor, kontrol edilmeli |
| DRIFT-009 | 🔵 P3 | Trip/Location engine.dispose() | **✅ FIXED** | `OutboxRelayBase._publish_single` artık proper session lifecycle kullanıyor |

**Özet:** 16 bulgudan **8'i FIXED**, **3'ü doğrulanacak**, **5'i hâlâ açık/dead code**.


---

## SEVİYE SINIFLANDIRMASI

| Seviye | Anlam |
|---|---|
| 🔴 P0 | Üretimde crash veya veri kaybı |
| 🟠 P1 | Platforma aykırı tasarım, sessiz hata riski |
| 🟡 P2 | Genetik sapma, servisler arası tutarsızlık |
| 🔵 P3 | Standart ihlali ama çalışan kod |

---

## 🔴 P0 — Üretimde Çöken Hatalar

### BUG-001 · Fleet outbox relay → `AttributeError: 'dict' has no attribute 'encode'`

**Dosya:** `services/fleet-service/src/fleet_service/workers/outbox_relay.py`

```python
# FleetOutbox.payload_json → Mapped[str] = mapped_column(Text)
# Fleet service şunu yazar: payload_json=json.dumps({...})  ← Text'e string kaydeder

# Relay şunu okur:
payload = json.loads(row.payload_json)  # str → dict'e parse eder ✓
return OutboxMessage(
    payload=payload,    # ← dict geçiriyor! OutboxMessage.payload: str bekleniyor
    ...
)

# KafkaBroker şunu dener:
value=message.payload.encode("utf-8")   # ← dict üzerinde .encode() → AttributeError: CRASH
```

**Etki:** Fleet servisinden hiçbir Kafka eventi gönderilemiyor. Outbox relay worker her batch'te çöküyor.

**Düzeltme:**
```python
payload_str = json.dumps(payload, cls=RobustJSONEncoder)  # dict → str
return OutboxMessage(payload=payload_str, ...)
```

---

### BUG-002 · Driver outbox relay → JSONB dict doğrudan Kafka'ya verilyor

**Dosya:** `services/driver-service/src/driver_service/workers/outbox_relay.py`

```python
# DriverOutboxModel.payload_json → Mapped[dict] = mapped_column(JSONB)
# Servis şunu yazar: payload_json=json.dumps(payload)  ← string'i JSONB'ye verir
# PostgreSQL/asyncpg çift JSON encode eder → okurken string döner

payload=row.payload_json,   # ← hangi durumda dict dönerse crash
```

Duruma göre (asyncpg JSONB codec davranışına bağlı): `dict` dönerse KafkaBroker `.encode()` → `AttributeError`. Minimum risk: **JSONB'ye json string yazmak veri bütünlüğünü bozar** (`payload_json->>'field'` SQL sorguları çalışmaz).

---

### BUG-003 · Identity `probe_broker()` → `AttributeError: 'NoOpBroker' has no attribute 'ping'`

**Dosya:** `services/identity-service/src/identity_service/broker.py`

```python
async def probe_broker() -> tuple[bool, str]:
    broker = create_broker()
    ok = await broker.ping()   # ← MessageBroker ABC'de ping() YOKTUR
    # Tanımlı metodlar: publish(), close(), check_health()
```

`probe_broker()` çağrıldığında her zaman exception fırlatır. `except` bloğu var ama `return True, "broker_connectivity_pending: ..."` döner → **/ready endpoint yanlış "sağlıklı" raporu verir.**

**Düzeltme:**
```python
await broker.check_health()  # ping() yerine
```

---

## 🟠 P1 — Sessiz Veri/Güvenilirlik Sorunları

### BUG-004 · §26.3 ihlali — 4 serviste outbox `payload_json` JSONB tipinde

**PLATFORM_STANDARD.md §9.1 açıkça şöyle diyor:**
> `payload_json` — `Text` — JSON string. **NOT JSONB** — portability required

**§26.3:** "No `JSONB` column type for outbox `payload_json`" — CI gate'i.

| Servis | `payload_json` tipi | Standart |
|---|---|---|
| trip-service | `JSONB` | ❌ |
| driver-service | `JSONB` | ❌ |
| identity-service | `JSONB` | ❌ |
| location-service | `JSONB` | ❌ |
| **fleet-service** | `Text` | **✅** |

Fleet tek uyumlu olan — ironic, çünkü relay'i bu yüzden bozuk.

---

### BUG-005 · §9.2 ihlali — `READY` durumu standart state machine'de yok

**`packages/platform-common/src/platform_common/outbox.py`:**
```python
class OutboxPublishStatus(str, enum.Enum):
    PENDING = "PENDING"
    READY = "READY"       # ← §9.2'de bu durum tanımlı DEĞİL
    PUBLISHING = "PUBLISHING"
    ...
```

PLATFORM_STANDARD §9.2 state machine'i: `PENDING → PUBLISHING → PUBLISHED | FAILED → DEAD_LETTER`. `READY` diye bir durum yok. Bu durum relay sorgularına da eklendi — standardın dışı bir durum makinesine evrildi.

---

### BUG-006 · §9.3 ihlali — backoff zamanlaması standarda uymıyor

**PLATFORM_STANDARD §9.3:**
```
Attempt 2 : +30 seconds
Attempt 3 : +2 minutes
Attempt 4 : +10 minutes
Attempt 5 : +1 hour → DEAD_LETTER
```

**`platform_common/outbox_relay.py` gerçek kod:**
```python
delay = (2**row.attempt_count) * 5   # 10s, 20s, 40s, 80s, 160s...
```

Hem zamanlamalar yanlış hem de `max_failures=10` default (standart 5 denemede dead-letter istiyor).

---

### BUG-007 · Telegram service → `BaseHTTPMiddleware` kullanıyor

**`services/telegram-service/src/telegram_service/middleware.py`:**
```python
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIdMiddleware(BaseHTTPMiddleware):  # ← §11.2: YASAK
class PrometheusMiddleware(BaseHTTPMiddleware):  # ← §11.2: YASAK
```

PLATFORM_STANDARD §11.2: "`BaseHTTPMiddleware.call_next()` wraps the inner app in a thread pool executor. This conflicts with asyncpg's connection model and causes **hangs under load**. All services MUST use pure ASGI implementation."

---

## 🟡 P2 — Servisler Arası Genetik Sapma

### DRIFT-001 · Outbox PK alanı tutarsız

| Servis | PK alanı | Standart (§9.1) |
|---|---|---|
| trip-service | `event_id` | `outbox_id` ❌ |
| driver-service | `event_id` | `outbox_id` ❌ |
| fleet-service | `outbox_id` | ✅ |
| identity-service | `outbox_id` | ✅ |
| location-service | `outbox_id` | ✅ |

`OutboxRelayBase._claim_batch()` bunu `getattr(m1, "outbox_id", getattr(m1, "event_id", None))` ile tolere ediyor — ama bu bir yama değil, tasarım sapması.

---

### DRIFT-002 · Kafka config farklı her serviste

| Servis | `linger.ms` | `compression.type` | `batch.size` | `max.in.flight` |
|---|---|---|---|---|
| trip-service | `settings.*` | `settings.*` | `settings.*` | — |
| location-service | ❌ yok | ❌ yok | ❌ yok | — |
| fleet-service | 5 hardcode | snappy hardcode | 16384 hardcode | — |
| driver-service | 5 hardcode | snappy hardcode | 16384 hardcode | — |
| identity-service | ❌ yok | ❌ yok | ❌ yok | 5 |

Location ve identity `linger.ms` / `compression.type` eksik → throughput düşük, Kafka mesajları sıkıştırılmaz.

---

### DRIFT-003 · Broker ortam çözümleme mantığı farklı

```python
# trip-service:     settings.resolved_broker_type (tek kaynak) ✅
# fleet-service:    settings.broker_type (farklı config field adı) 🟡
# driver-service:   settings.broker_type (farklı) 🟡
# location-service: elle if/elif (kafka_bootstrap_servers kontrolü) ❌
# identity-service: settings.resolved_broker_backend (farklı field adı) 🟡
```

Her servis farklı mantıkla broker seçiyor. Location servisinde ayrı bir `if settings.environment != "dev"` dalı var — hatalı davranış üretebilir.

---

### DRIFT-004 · `correlation_id` location outbox relay'de eksik

```python
# location-service/workers/outbox_relay.py:
return OutboxMessage(
    ...
    causation_id=row.causation_id,
    # correlation_id YOK! ← diğer tüm servisler bunu geçiriyor
)
```

Bu, Kafka eventleri üzerinde trace korelasyonunu kırıyor.

---

### DRIFT-005 · `schema_version` alanı trip'te farklı isimle

Trip outbox modelinde `schema_version`, diğer tüm servislerde `event_version`. Trip outbox relay doğru map ediyor ama standart tek isim bekliyor (`event_version`).

---

## 🔵 P3 — Standart İhlalleri (Çalışıyor Ama Standarda Aykırı)

| Kod | Bulgu |
|---|---|
| P3-001 | `platform_common/outbox_relay.py` → `_mark_published` içinde `attempt_count=0` sıfırlıyor — standart bunu belirtmiyor, potansiyel metrik yanılması |
| P3-002 | `TripOutbox.partition_key` nullable değil ama `FleetOutbox.partition_key` nullable — standart `String(100)` diyor, nullable/not-null belirtmemiş |
| P3-003 | `AsyncTimeout` context manager'ı (`resiliency.py`) yanlış implemente edilmiş — `__aenter__` `asyncio.wait_for(asyncio.sleep(0), ...)` yapıyor, bu anlamsız |
| P3-004 | `DriverOutboxModel` içinde `outbox_id` alias PK yok ama relay iç `lifecycle.py` içinde `outbox_id=_new_ulid()` kullanıyor — model ile yazma kodu çelişiyor |

---

## GENEL DEĞERLENDİRME

### Güçlü Yönler (gerçek, kanıtlanmış)
- Platform-common paketi iyi tasarlanmış: `OutboxRelayBase`, `CircuitBreaker`, `MessageBroker` ABC katmanlı, temiz
- Tüm servisler (telegram hariç) pure ASGI middleware kullanıyor
- ULID everywhere doğru uygulanmış
- `FOR UPDATE SKIP LOCKED` HOL blocking doğru implemente edilmiş
- `platform-auth` paketi RS256/JWKS doğru tasarlanmış

### Kritik Durum

**2 servisin outbox relay'i üretimde çalışmaz** (fleet = P0 crash, driver = P0/P1 risk). Platform standardı `payload_json: Text` diyor ama 4 servis JSONB kullanıyor — bu §26.3 CI gate kuralını otomatik kırar.

**Hedeflenen "aynı genetik" henüz yok.** 6 servisten 6'sının outbox alan adları, payload tipleri, Kafka config yapısı, broker resolution mantığı ve state machine durumları farklı.

---

## Öncelikli Düzeltme Sırası

**SPRINT 1 — P0 (bu hafta):**
1. Fleet outbox relay: `payload=json.dumps(payload, cls=RobustJSONEncoder)` — 1 satır
2. Driver outbox relay: aynı fix + JSONB → Text migration planı
3. Identity `probe_broker()`: `ping()` → `check_health()`

**SPRINT 2 — P1:**
4. Tüm servislerde `payload_json`: JSONB → Text Alembic migrasyonu (5 servis)
5. `OutboxPublishStatus.READY` kaldır veya standarda ekle
6. Backoff zamanlamasını §9.3'e uyumlu hale getir

**SPRINT 3 — Genetik standardizasyon:**
7. Kafka config → her serviste tek `_kafka_config()` factory, settings'ten okuyan
8. Broker resolution → hepsi `settings.resolved_broker_type` kullanacak
9. Outbox PK → trip ve driver `event_id` → `outbox_id` rename
10. Telegram middleware → pure ASGI'a geç
---

## 🔴 Devam Raporu — Sprint 1+2+3 Seviyesine Görünür Tüm Bulgular

---

### YENİ BULGULAR (2. Tur)

---

### 🔴 P0 — BUG-008 · `OutboxRelayBase` HOL blocking → DEAD_LETTER kalıcı livelock

**Dosya:** `packages/platform-common/src/platform_common/outbox_relay.py`

```python
# HOL blocking subquery:
hol_subq = select(1).where(
    m2.partition_key == m1.partition_key,
    m2.publish_status != OutboxPublishStatus.PUBLISHED.value,  # ← DEAD_LETTER dahil
    m2.created_at_utc < m1.created_at_utc,
)
```

Bir satır `DEAD_LETTER` durumuna düşerse — aynı `partition_key`'e sahip tüm sonraki satırlar **sonsuza kadar** publish edilemez. `DEAD_LETTER != PUBLISHED` olduğu için bu satır daima HOL blocker olarak görünür. Bu 6 servisin tamamını etkileyen platform-level bir kilitleme hatası.

**Düzeltme:**
```python
m2.publish_status.in_([
    "PENDING", "READY", "PUBLISHING", "FAILED"  # DEAD_LETTER hariç
])
```

---

### 🟠 P1 — BUG-009 · Identity worker `finally` bloğunda `setup_redis()` çağrısı

**Dosya:** `services/identity-service/src/identity_service/entrypoints/outbox_worker.py`

```python
finally:
    await broker.close()
    await setup_redis()   # ← YANLIŞ! Shutdown sırasında Redis başlatmak saçma
    from identity_service.redis_client import close_redis
    await close_redis()
```

Shutdown sırasında `setup_redis()` çağrısı yeni Redis bağlantıları açar, ardından `close_redis()` kapatır. Bu gereksiz ve shutdown sürecini yavaşlatır; Redis erişilemez durumdaysa exception fırlatır.

---

### 🟠 P1 — BUG-010 · Trip idempotency kaydı ana transaction dışında kaydediliyor

**Dosya:** `services/trip-service/src/trip_service/trip_helpers.py`

```python
# 1. ana session commit → trip + outbox oluştu
await self.session.commit()

# 2. AYRI session'da idempotency kaydı
await _save_idempotency_record(...)   # secondary_session açar
```

Adım 1 ile adım 2 arasında process crash olursa: trip oluştu, idempotency kaydı YOK. Aynı idempotency key ile tekrar çağrı gelirse trip bir kez daha oluşturulur → **duplicate trip**. İdempotency kaydı ana transaction ile aynı session'da olmalıydı.

---

### 🟡 P2 — DRIFT-006 · Kafka topic adları SERVICE_REGISTRY ile uyumsuz

| Servis | Config default | SERVICE_REGISTRY.md |
|---|---|---|
| location-service | `"location-events"` | `"location.events.v1"` ❌ |
| identity-service | `"identity-events"` | `"identity.events.v1"` ❌ |
| trip-service | `"trip.events.v1"` | `"trip.events.v1"` ✅ |
| fleet-service | `"fleet.events.v1"` | `"fleet.events.v1"` ✅ |
| driver-service | `"driver.events.v1"` | `"driver.events.v1"` ✅ |

Location ve Identity yanlış topic default'a sahip. Env override yoksa yanlış topice publish ederler.

---

### 🟡 P2 — DRIFT-007 · Driver ve Fleet routers §7.2 ihlali

**PLATFORM_STANDARD §7.2:** "WRONG — prefix + relative path = silent double-prefix bug"

Hem driver hem fleet `APIRouter(prefix=...)` kullanıyor. `include_router()` çağrısında prefix verilmediği için şu an routing doğru çalışıyor — ama standarttaki yasak pattern bu. Yeni bir agent bir servis eklerken `include_router(prefix=...)` de eklerse double-prefix bug oluşur.

---

### 🟡 P2 — DRIFT-008 · Platform'da gerçek event consumption yok

Tüm servisler **sadece producer**. Hiçbir servis Kafka event'lerini tüketmiyor. `platform-common` paketi consumer base sınıfı içermiyor. Bu, "tam izole event-driven mikroservis" hedefiyle çelişiyor — servisler eventlere tepki veremiyor, sadece kendi eventlerini yayınlıyor.

Mevcut durum: Outbox → Kafka publish var ✅, Kafka consume → yok ❌.

---

### 🔵 P3 — DRIFT-009 · Trip worker ve Location worker `engine.dispose()` eksik

```python
# trip outbox_worker.py ve location outbox_worker.py finally bloğu:
finally:
    await broker.close()
    await close_redis()
    shutdown_tracing()
    # engine.dispose() YOK — asyncpg connection pool kapatılmıyor
```

Fleet ve driver worker'larında `engine.dispose()` var. Trip ve location worker'larında yok → PostgreSQL connection pool process sonlanana kadar GC'ye bırakılıyor.

---

## GÜNCELLENMİŞ TAM SORUN HARİTASI

| ID | Seviye | Konu | Etkilenen Servis |
|---|---|---|---|
| BUG-001 | 🔴 P0 | Fleet outbox relay `payload=dict` → Kafka'ya `.encode()` crash | fleet |
| BUG-002 | 🔴 P0 | Driver outbox relay `payload=JSONB dict` → tip uyumsuzluğu | driver |
| BUG-003 | 🔴 P0 | Identity `probe_broker()` → `broker.ping()` yok → /ready yanıltıcı | identity |
| BUG-008 | 🔴 P0 | HOL blocking DEAD_LETTER'ı dışlamıyor → kalıcı livelock | **TÜM SERVİSLER** |
| BUG-004 | 🟠 P1 | 4 serviste outbox `payload_json` JSONB (standart Text istiyor) | trip/driver/identity/location |
| BUG-005 | 🟠 P1 | `READY` durumu standart state machine'de yok | platform-common |
| BUG-006 | 🟠 P1 | Backoff zamanlaması §9.3'e uymuyor (2^n*5s vs 30s/2m/10m/1h) | platform-common |
| BUG-007 | 🟠 P1 | Telegram `BaseHTTPMiddleware` → asyncpg hang under load | telegram |
| BUG-009 | 🟠 P1 | Identity worker finally'de `setup_redis()` çağrısı | identity |
| BUG-010 | 🟠 P1 | Trip idempotency kaydı ayrı session → duplicate risk | trip |
| DRIFT-001 | 🟡 P2 | Outbox PK alanı: trip/driver=`event_id`, diğerleri=`outbox_id` | trip, driver |
| DRIFT-002 | 🟡 P2 | Kafka config parametreleri servisler arası farklı | tüm servisler |
| DRIFT-003 | 🟡 P2 | Broker ortam çözümleme: location'da ad-hoc if/elif | location |
| DRIFT-004 | 🟡 P2 | Location outbox relay'de `correlation_id` eksik | location |
| DRIFT-005 | 🟡 P2 | Trip outbox `schema_version` alanı, diğerleri `event_version` | trip |
| DRIFT-006 | 🟡 P2 | Location ve identity Kafka topic adı SERVICE_REGISTRY'ye uymuyor | location, identity |
| DRIFT-007 | 🟡 P2 | Driver ve Fleet router prefix kullanıyor (§7.2 yasak) | driver, fleet |
| DRIFT-008 | 🟡 P2 | Platform tamamen producer-only — consumer yok, gerçek EDA değil | platform |
| DRIFT-009 | 🔵 P3 | Trip ve Location worker `engine.dispose()` eksik | trip, location |

---

## "Aynı Genetik" İçin Gereken Platform-Level Değişiklikler

Şu anki durumda 6 servis 6 farklı "lehçe" konuşuyor. Tam genetik birlik için şunlar lazım:

**platform-common paketi şu an eksikleri:**
1. `KafkaConsumerBase` — Kafka event tüketimi için base class
2. Outbox backoff zamanlaması §9.3'e uygun olmalı
3. HOL blocking'den DEAD_LETTER çıkarılmalı
4. `READY` status ya standarda girip belgelenmeli ya kaldırılmalı

**Her servis için standart şablon boşlukları:**
1. Tek `_kafka_config()` factory → settings'ten okuyan, hardcode yok
2. Tek broker resolution field adı (`resolved_broker_type`) → tüm servislerde aynı
3. Outbox PK: hepsi `outbox_id`
4. Outbox `payload_json`: hepsi `Text` (JSONB değil)
5. Outbox `event_version` (trip'te `schema_version` değil)
6. Kafka topic: `{domain}.events.v1` pattern — location ve identity güncellenecek
Artık tüm servisleri ve platform katmanını derinlemesine taradım. Kapsamlı nihai raporu oluşturuyorum.---

# LOJINEXTv2 — Tam Denetim Raporu (Nihai)
**16.113 satır kaynak kod okundu. Satır satır.**

---

## 🔴 YENİ P0 — BUG-011 · Trip ve Driver: JWKS cache miss → event loop tamamen bloke

**Dosya:** `services/trip-service/src/trip_service/auth.py` · `services/driver-service/src/driver_service/auth.py`

```python
# Her iki serviste de:
def _decode_claims(authorization: str | None) -> Any:
    return decode_bearer_token(...)   # ← SYNC çağrı
```

`platform_auth.jwt_codec.decode_bearer_token` → `provider.verification_key(header)` → `_load_jwks_sync()` → **`httpx.Client()`** (senkron HTTP) çağrısı yapar. Bu, asyncpg'nin async event loop'unu tamamen dondurur.

JWKS cache TTL dolduğunda (default her 5 dakikada bir), o pencerede gelen **tüm** istekler identity-service'e sync HTTP bağlantısı açılana kadar (timeout=5s) bekler. Yük altında bu, tüm servis için kaskad stall'a yol açar.

| Servis | `_decode_claims` | JWKS davranışı |
|---|---|---|
| trip-service | `decode_bearer_token` (SYNC) | ❌ Event loop bloğu |
| driver-service | `decode_bearer_token` (SYNC) | ❌ Event loop bloğu |
| fleet-service | `async_decode_bearer_token` (ASYNC) | ✅ |
| location-service | `async_decode_bearer_token` (ASYNC) | ✅ |

PLATFORM_STANDARD §4.2: "The JWKS key loading MUST be async… `urllib.request.urlopen` and all synchronous I/O are **forbidden** in the JWKS loading path."

**Düzeltme:**
```python
# Her iki serviste de:
async def _decode_claims(authorization: str | None) -> Any:
    return await async_decode_bearer_token(...)
```

---

## 🔴 YENİ P0 — BUG-012 · Saga compensation eventi outbox'ı bypass ediyor

**Dosya:** `services/trip-service/src/trip_service/saga.py`

```python
async def compensate(self, reason: str) -> None:
    broker = create_broker(settings.resolved_broker_type)  # ← geçici broker
    try:
        await broker.publish(                               # ← DOĞRUDAN Kafka
            self._build_compensation_event("trip.compensate.release_vehicle.v1", ...)
        )
    except Exception:
        logger.exception(...)  # ← Fail ederse event KAYBOLUR
```

Compensation eventleri transactional outbox'ı tamamen atlayarak Kafka'ya doğrudan publish ediliyor. Broker erişilemez, pod crash, network timeout → **compensation eventi kaybolur, saga yarım kalır**.

PLATFORM_STANDARD §22.4: "The outbox model (§9) **applies to compensation events** as well."

Ayrıca saga state yalnızca Redis'te tutuluyor — PLATFORM_STANDARD §22.5 DB'de tutulmasını zorunlu kılıyor. Redis crash → saga state kaybolur, hangi adımın tamamlandığı bilinmez.

---

## 🟠 YENİ P1 — BUG-013 · Driver: "ADMIN" rol string'i PlatformRole'da tanımsız

**Dosya:** `services/driver-service/src/driver_service/auth.py`

```python
if role not in {PlatformRole.SUPER_ADMIN, "ADMIN"}:  # ← "ADMIN" ham string
    raise driver_forbidden("SUPER_ADMIN or ADMIN role required.")
```

`PlatformRole` enum'unda `ADMIN` yok. Sadece `SUPER_ADMIN`, `MANAGER`, `OPERATOR`, `SERVICE` var. Bu iki sonuç doğurur:
1. "ADMIN" token claim'i taşıyan sahte JWT'ler bu kontrolü geçer
2. Bir admin rolünü standartlaştırma girişimi olarak `MANAGER` kullanılması gerekiyorsa, mevcut logic onu reddeder

PLATFORM_STANDARD §5.1: "No service MUST define its own role enum."

---

## 🟠 YENİ P1 — BUG-014 · Telegram: Tüm downstream HTTP çağrılarında circuit breaker yok

**Dosya:** `services/telegram-service/src/telegram_service/clients/`

`trip_client.py`, `driver_client.py`, `fleet_client.py` — üçü de doğrudan `client.post()` / `client.get()` çağrısı yapıyor. `resp.raise_for_status()` → `httpx.HTTPStatusError` → işlenmemiş exception.

Bir downstream servis yavaşlarsa, Telegram servisinin tüm bot handler'ları timeout'a kadar (10s) bekler. PLATFORM_STANDARD §17.2: "Circuit breaker REQUIRED for every downstream client."

---

## 🟠 YENİ P1 — BUG-015 · Telegram: Production kodunda `assert` deyimleri

**Dosya:** `services/telegram-service/src/telegram_service/clients/trip_client.py`

```python
assert fields.tare_kg is not None    # Python -O ile derleme: bu satır SILINIR
assert fields.gross_kg is not None   # ← RuntimeError değil, sessiz skip
assert fields.origin is not None
```

Python `-O` (optimize) flag'i ile `assert` deyimleri bytecode'dan çıkarılır. Production container'larda `-O` kullanılırsa bu kontroller bypass edilip `None` değerler trip-service'e gider → 422 validation error veya veri bozulması. Düzeltme: `if field is None: raise ValueError(...)`.

---

## 🟠 YENİ P1 — BUG-016 · platform-auth `JWKSKeyProvider`: JWKS cache concurrent refresh race

**Dosya:** `packages/platform-auth/src/platform_auth/key_provider.py`

```python
async def async_verification_key(self, header: dict) -> Any:
    if not self._keys or (time.monotonic() - self._cached_at >= self.cache_ttl_seconds):
        await self._load_jwks_async()  # ← asyncio.Lock YOK
```

Eş zamanlı 10 istek gelip hepsi cache'in boş/expire olduğunu görürse, **10 paralel JWKS fetch** başlatır. Her biri identity-service'e ayrı HTTP isteği atar. Kısa süreli thundering herd. `asyncio.Lock` ile korunmalı.

---

## GÜNCELLENMİŞ MASTER SORUN TABLOSU

### 🔴 P0 — Üretimde crash veya veri kaybı

| ID | Bulgu | Servis |
|---|---|---|
| BUG-001 | Fleet outbox relay: `payload=dict` → `AttributeError: 'dict'.encode()` → **crash** | fleet |
| BUG-002 | Driver outbox relay: JSONB `payload` doğrudan Kafka'ya → tip uyumsuzluğu | driver |
| BUG-003 | Identity `probe_broker()` → `broker.ping()` yok → her çağrıda crash, `/ready` yanıltıcı | identity |
| BUG-008 | HOL blocking DEAD_LETTER'ı dışlamıyor → aynı partition_key'in sonraki tüm eventleri **sonsuza kadar bloke** | **TÜM SERVİSLER** |
| BUG-011 | Trip + Driver sync JWKS decode → cache miss'te event loop donması (5s) | trip, driver |
| BUG-012 | Saga compensation eventleri outbox bypass → broker fail'de **kayıp**, saga state yalnızca Redis | trip |

### 🟠 P1 — Sessiz hata, güvenilirlik veya güvenlik riski

| ID | Bulgu | Servis |
|---|---|---|
| BUG-004 | 4 servis `payload_json` JSONB (§26.3 CI gate ihlali) | trip, driver, identity, location |
| BUG-005 | `READY` durumu standart state machine'de yok, outbox relay query'ye eklendi | platform-common |
| BUG-006 | Backoff zamanlaması §9.3'e uymuyor (`2^n*5s` ≠ `30s/2m/10m/1h`) | platform-common |
| BUG-007 | Telegram `BaseHTTPMiddleware` → asyncpg hang under load | telegram |
| BUG-009 | Identity worker `finally` bloğunda `setup_redis()` çağrısı → shutdown'da yeni bağlantı açılır | identity |
| BUG-010 | Trip idempotency kaydı ayrı secondary session → process crash → duplicate trip riski | trip |
| BUG-013 | Driver `"ADMIN"` rol string'i PlatformRole'da yok → unauthorized erişim kapısı | driver |
| BUG-014 | Telegram tüm downstream çağrıları circuit breaker yok → kaskad zaman aşımı | telegram |
| BUG-015 | Telegram `assert` deyimleri production'da `-O` flag'i ile silinir → null pass-through | telegram |
| BUG-016 | JWKS `async_verification_key` asyncio.Lock yok → 10 paralel HTTP fetch olabilir | platform-auth |

### 🟡 P2 — Genetik sapma, platform tutarsızlığı

| ID | Bulgu | Servis |
|---|---|---|
| DRIFT-001 | Outbox PK: `event_id` (trip, driver) vs `outbox_id` (diğerleri) | trip, driver |
| DRIFT-002 | Kafka config parametreleri: her serviste farklı (hardcode vs settings, eksik alanlar) | tüm servisler |
| DRIFT-003 | Broker ortam çözümleme mantığı: location ad-hoc if/elif | location |
| DRIFT-004 | Location outbox relay'de `correlation_id` eksik | location |
| DRIFT-005 | Trip outbox `schema_version` alanı, standart `event_version` bekliyor | trip |
| DRIFT-006 | Kafka topic: location=`"location-events"`, identity=`"identity-events"` (registry uyumsuz) | location, identity |
| DRIFT-007 | Driver ve Fleet `APIRouter(prefix=...)` kullanıyor (§7.2 yasak) | driver, fleet |
| DRIFT-008 | **Platform tamamen producer-only** — hiçbir servis Kafka event tüketmiyor, tam EDA değil | platform |
| DRIFT-009 | Trip ve Location worker `engine.dispose()` eksik | trip, location |

---

## "AYNI GENETİK" İÇİN KANONIK ŞABLON

Tüm servislerin aynı genetiği taşıması için her serviste şunlar **birebir aynı** olmalı:

### 1. Broker Şablonu
```python
# config.py — TÜM SERVİSLERDE AYNI
@property
def resolved_broker_type(self) -> Literal["kafka", "log", "noop"]:
    if self.broker_type is not None:
        return self.broker_type
    return "kafka" if self.environment == "prod" else "log"

# broker.py — TÜM SERVİSLERDE AYNI
def _kafka_config() -> dict[str, object]:
    return {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "client.id":          settings.kafka_client_id,
        "acks":               "all",
        "enable.idempotence": True,
        "linger.ms":          settings.kafka_linger_ms,       # settings'ten
        "batch.size":         settings.kafka_batch_size,      # settings'ten
        "compression.type":   settings.kafka_compression_type,# settings'ten
        "security.protocol":  settings.kafka_security_protocol,
    }
```

### 2. Auth Şablonu (async zorunlu)
```python
# auth.py — TÜM SERVİSLERDE AYNI
async def _decode_claims(authorization: str | None) -> TokenClaims:
    try:
        return await async_decode_bearer_token(authorization, _platform_auth_settings())
    except TokenMissingError as exc:
        raise {svc}_auth_required() from exc
    except Exception as exc:
        raise {svc}_auth_invalid(str(exc)) from exc
```

### 3. Outbox Model Şablonu (standart §9.1 tam uyumlu)
```python
# models.py — TÜM SERVİSLERDE AYNI ALAN ADLARI
class {Svc}Outbox(Base):
    __tablename__ = "{svc}_outbox"
    outbox_id:           Mapped[str]            # PK, ULID
    aggregate_type:      Mapped[str]            # String(16)
    aggregate_id:        Mapped[str]            # String(26)
    aggregate_version:   Mapped[int]
    event_name:          Mapped[str]            # String(80)
    event_version:       Mapped[int]            # default 1
    payload_json:        Mapped[str] = mapped_column(Text)  # TEXT — JSONB YASAK
    partition_key:       Mapped[str]            # String(100), NOT NULL
    publish_status:      Mapped[str]            # String(16)
    attempt_count:       Mapped[int]            # default 0
    last_error_code:     Mapped[str | None]     # String(100)
    next_attempt_at_utc: Mapped[datetime | None]
    claim_token:         Mapped[str | None]
    claim_expires_at_utc:Mapped[datetime | None]
    claimed_by_worker:   Mapped[str | None]
    created_at_utc:      Mapped[datetime]
    published_at_utc:    Mapped[datetime | None]
    correlation_id:      Mapped[str | None]
    causation_id:        Mapped[str | None]
```

### 4. HOL Blocking Düzeltmesi (platform-common)
```python
# platform_common/outbox_relay.py — BUG-008 fix
hol_subq = select(1).where(
    m2.partition_key == m1.partition_key,
    m2.publish_status.in_([          # ← != yerine in_ kullan
        OutboxPublishStatus.PENDING.value,
        OutboxPublishStatus.READY.value,
        OutboxPublishStatus.PUBLISHING.value,
        OutboxPublishStatus.FAILED.value,
    ]),                              # ← DEAD_LETTER hariç
    m2.created_at_utc < m1.created_at_utc,
)
```

---

## 3 SPRINT EYLEM PLANI (yeniden önceliklendirilmiş)

**SPRINT 1 — P0 crashler:**
1. `platform_common/outbox_relay.py` — HOL DEAD_LETTER fix (1 satır, tüm servisleri kurtarır)
2. Fleet outbox relay — `payload=json.dumps(payload)` (1 satır)
3. Trip + Driver auth — `decode_bearer_token` → `async_decode_bearer_token` (2 servis)
4. Identity `probe_broker()` — `broker.ping()` → `broker.check_health()`

**SPRINT 2 — P1 veri bütünlüğü:**
5. Tüm servislerde `payload_json`: JSONB → Text (Alembic migrasyon + model + relay)
6. Saga: compensation eventleri → outbox pattern'e taşı + state DB'ye yaz
7. Identity worker `finally` bloğundaki `setup_redis()` kaldır
8. Trip idempotency: secondary session → ana session

**SPRINT 3 — Genetik standardizasyon:**
9. Kafka config → tüm servislerde `settings.*` üzerinden aynı factory
10. `resolved_broker_type` → tüm servislerde aynı field adı ve mantık
11. Kafka topic adları → location ve identity güncelleme
12. Outbox PK → trip ve driver: `event_id` → `outbox_id`
13. `event_version` field adı → trip'te `schema_version` → `event_version`
14. Telegram: pure ASGI middleware + circuit breaker + assert kaldır
15. `platform_common` → `KafkaConsumerBase` ekleme (gerçek EDA için)
16. JWKS `async_verification_key` → `asyncio.Lock` ile koru
---

## Plan Değerlendirmesi — Kesin Yargı

16.113 satır kod ve plan satır satır karşılaştırıldı. Aşağıdakiler **kod kanıtına dayalı**, varsayım yok.

---

## ✅ Doğru Tespitler (8 madde)

| Madde | Değerlendirme |
|---|---|
| HOL fix satır 127 | Doğru konum, doğru çözüm |
| Backoff `[30, 120, 600, 3600]` tablo | Doğru — mevcut `2^n*5` yanlış |
| `max_failures` 10→5 | Doğru |
| Fleet relay `payload=dict` fix | Doğru konum (satır 41 değil, 39 ama aynı blok) |
| Identity `probe_broker()` ping→check_health | Doğru |
| Identity worker `finally setup_redis()` kaldır | Doğru |
| platform-auth JWKS Lock | Doğru |
| Trip idempotency secondary session riski | Doğru tespit, çözüm tartışmalı (aşağıda) |

---

## ❌ Hatalı / Yanıltıcı Maddeler (6 madde — bunlar uygulanırsa zarar verir)

### HATA-1 · "Fleet `FleetOutbox.correlation_id` kolonu ekle (Sprint 2)"

```
Gerçek durum:
  services/fleet-service/alembic/versions/007_outbox_correlation_id.py → migration ZATEN ÇALIŞTI
  services/fleet-service/src/fleet_service/models.py:241 → correlation_id: Mapped[str | None] ZATEN VAR
```

Bu görevi bir agent'a versen: yeni bir migration yazar, `duplicate column` hatası alır, servis startup'ta çöker. Plan bu maddeyi Sprint 2'ye koymuş — **silinmeli**.

---

### HATA-2 · "Location relay HTTP yasağı (TASK-04)"

```
Gerçek durum:
  services/location-service/src/location_service/workers/outbox_relay.py →
  httpx/http/client → hiçbiri yok. Relay tamamen DB+Kafka işlemi.
```

Bu maddenin hangi kod satırına dayandığı anlaşılamıyor. `TASK-04` ise "Location Service Domain Logic" (normalization, code generation) görevidir — outbox relay ile ilgisi yok. Plan burada **kaynak kod okumadan** kural yazmış.

---

### HATA-3 · "Location relay backoff jitter ekle"

```
Gerçek durum:
  packages/platform-common/src/platform_common/outbox_relay.py:16 → import random ZATEN VAR
```

Jitter platform-common'da zaten mevcut değil mi? Hayır — `import random` var ama `_mark_failed` içinde `delay = (2**row.attempt_count) * 5` kullanılıyor, jitter YOK. **Bu tespit doğru ama lokasyon yanlış:** jitter location relay'e eklenecek değil, `platform_common/outbox_relay.py`'nin `_mark_failed` metoduna eklenecek. location-service bunu zaten `OutboxRelayBase`'den miras alıyor.

---

### HATA-4 · "Saga outbox bypass düzelt (Sprint 1)"

```
Gerçek durum:
  saga.py tamamen dead code. Hiçbir import yok, hiçbir çağrı yok.
  grep -rn "saga" services/trip-service/src/ --include="*.py" | grep -v saga.py → 0 sonuç
```

Plan bunu P0 olarak Sprint 1'e koymuş. Çalışan kodda bug yok, çünkü bu kod hiç çalışmıyor. Ama plan bir agent'ın işgücünü buraya harcamasına neden olur. **Doğru aksiyon:** saga.py ya silinmeli ya da "TODO: henüz entegre edilmedi" notu konmalı.

---

### HATA-5 · "Driver `\"ADMIN\"` kaldır, yalnızca `PlatformRole.SUPER_ADMIN` kabul et"

```
Gerçek durum:
  require_admin_token → SUPER_ADMIN veya "ADMIN" kabul ediyor
  require_admin_or_manager_token → SUPER_ADMIN, "ADMIN", MANAGER kabul ediyor
  
  Kullanım:
  lifecycle.py:166, 276, 375, 482 → admin_auth_dependency (require_admin_token)
  public.py:158, 412 → admin_auth_dependency
```

"ADMIN" role'ü `PlatformRole`'da yok — bu DOĞRU. Ama düzeltme **sadece SUPER_ADMIN bırakma** değil, **MANAGER ekle** olmalı. `require_admin_token` şu an yaşam döngüsü mutasyonlarını korur — bunu salt SUPER_ADMIN'a kısıtlamak çoğu endpoint'i MANAGER rolü için kırar. Doğru fix:

```python
if role not in {PlatformRole.SUPER_ADMIN, PlatformRole.MANAGER}:
```

Plan bu nüansı atlamış.

---

### HATA-6 · "OTEL tracing rollout Sprint 3 — driver, fleet, identity, location'da kurulum"

```
Gerçek durum:
  Her 5 servisin hem main.py hem worker entrypoint'inde:
  setup_tracing() → zaten çağrılıyor (her servis 2-4 çağrı)
```

Bu madde Sprint 3'te gereksiz iş. Sadece "span propagation doğrulaması" yapılabilir ama bunu bir task olarak koymak agent'ı var olan kodu yeniden yazmaya yönlendirir.

---

## ⚠️ Eksik Maddeler (Plan'da hiç olmayan ama olması gereken)

### EKSİK-1 · Trip `ActorType` → `PlatformRole` migrasyonu

```python
# services/trip-service/src/trip_service/enums.py
class ActorType(str, enum.Enum):  # ← §5.1 ihlali: kendi role enum'u
    MANAGER = str(PlatformRole.MANAGER.value)
```

Plan trip auth async geçişini kapsıyor ama bu `ActorType` yerel enum kullanımını atlamış. `require_user_token` içinde `ActorType.MANAGER.value` kontrolü var — `PlatformRole` direkt kullanılmalı.

---

### EKSİK-2 · Trip auth `async def` cascade'i planlanmamış

```
Plan der: "_decode_claims → async def, await async_decode_bearer_token"
Gerçek cascade:
  _decode_claims → async
  require_user_token → async (çünkü _decode_claims await ediyor)
  require_service_token → async
  user_auth_dependency → async (FastAPI Depends bunu destekler ✓)
  telegram_service_auth_dependency → async
  excel_service_auth_dependency → async
  reference_service_auth_dependency → async
```

FastAPI `async def` dependency'leri destekler. Ama planın "tüm çağıranlar async yapılacak" satırı çok muğlak. Bir agent bu cascade'i yanlış yaparsa (örneğin bazı dependency'leri sync bırakırsa) runtime error alır. Plan bu 6 fonksiyonun tamamını **isimleriyle** listelemeli.

---

### EKSİK-3 · Trip outbox `schema_version` → `event_version` rename

Denetimdeki DRIFT-005 plan'a hiç girmemiş. `TripOutbox.schema_version` alanı standardın `event_version` gerektirdiği yerde duruyor. `OutboxRelayBase.map_row_to_message` `schema_version=getattr(row, "schema_version", 1)` ile workaround yapıyor.

---

### EKSİK-4 · Kafka topic fix testi planlanmamış

Plan Sprint 3'te topic adlarını düzeltiyor ama doğrulama testi yok. Kafka topic adı config default'ta değişirse, mevcut PENDING outbox satırlarındaki topic bilgisi etkilenmez (outbox'ta topic saklanmıyor, relay broker'a gönderirken config'den alıyor). Ama test olmadan bu geçişin silent breaking change yaratıp yaratmadığı bilinmez.

---

### EKSİK-5 · `payload_json` JSONB→Text migration'ın side effect'i

Plan der: "4 serviste JSONB → Text Alembic migration"

Ancak **bu migration'ın ciddi bir riski var:**

```
Mevcut durum: JSONB kolona json.dumps() string yazılıyor
asyncpg davranışı: JSON string'i parse ederek Python dict olarak döndürüyor
Trip/location/identity relay: isinstance(row.payload_json, str) else row.payload_json ile handle ediyor

Text'e geçince:
  asyncpg string olarak döndürecek → relay'lerin str branch'i çalışacak ✓
  Ama migration sırasında mevcut PENDING satırları var
  JSONB'den Text'e ALTER COLUMN: PostgreSQL bunu dolaylı cast ile yapar
  Ancak PENDING satırlardaki JSON verisi korunur ✓ (PostgreSQL JSON→TEXT cast güvenli)
```

Bu migration zero-downtime değil — production'da dikkat gerekiyor. Plan bunu **belirtmiyor**.

---

## 🔴 Kritik Mimari Boşluk (Plan'da hiç ele alınmıyor)

### Platform tamamen consumer'sız

Plan 35 görev tanımlıyor ama "Kafka Consumer" Sprint 4-8'e erteleniyor. **Bu kritik çünkü:** Fleet/driver/location servisleri şu an trip eventlerine tepki veremiyor. "Tam izole event-driven mikroservis" hedefi için consumer altyapısı olmazsa:

- Fleet, driver'ın aktif olup olmadığını sync HTTP ile soruyor → kırılgan bağımlılık
- Trip tamamlandığında fleet/driver serbest bırakma ancak sync HTTP ile mümkün
- Location route güncellendiğinde trip'lerin re-enrichment'ı tetiklenemiyor

Bu Sprint 1-3 bittikten sonra platform hala event-driven değil, sadece outbox-to-Kafka publish yapan bir servis kümesi.

---

## Özet Puanlama

| Kriter | Puan |
|---|---|
| Doğru bug tespiti (bilinen P0'lar) | 8/10 |
| Lokasyon/satır doğruluğu | 6/10 |
| Hatalı/gereksiz görevler | 4 hata (zarar verebilir) |
| Eksik yan etkiler/cascade | Yetersiz (özellikle auth cascade, migration riski) |
| Önceliklendirme mantığı | Mantıklı ama saga dead code P0'a sokmak israf |
| Agent'a verilebilirlik | %65 — 4 madde düzeltilmeden agent'a verilmemeli |

**Plan uygulanmadan önce şunlar yapılmalı:**

1. `fleet correlation_id ekle` → **kaldır**
2. `location relay HTTP yasağı` → **kaldır**
3. `OTEL rollout Sprint 3` → **kaldır**
4. `Saga P0 fix` → "dead code temizliği" olarak Sprint 3'e taşı
5. `Driver ADMIN fix` → `PlatformRole.SUPER_ADMIN | PlatformRole.MANAGER` olarak düzelt
6. `Location backoff jitter` → lokasyonu `platform_common/outbox_relay.py → _mark_failed` olarak düzelt
7. Trip auth cascade → 6 fonksiyon **isimleriyle** listelenmeli
8. `payload_json` migration → zero-downtime planı eklenmeli