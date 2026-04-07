# Trip Service — Derin Analiz Raporu

> Tarih: 2026-04-06
> Analiz kapsamı: `services/trip-service`, `services/driver-service`, ilgili platform paketleri ve MEMORY dosyaları

---

## 1. Mevcut Durum

### 1.1 Trip Service Kod Durumu

Trip service, üretim kalitesine yakın bir noktada. Temel özellikler gerçeklenmiş:

| Katman | Durum | Not |
|---|---|---|
| ORM Modelleri | ✅ Tam | Trip, Evidence, Enrichment, Timeline, Outbox, Audit, Idempotency, Heartbeat |
| Pydantic Şemalar | ✅ Tam | Request/response ayrımı net, RFC 9457 error format uygulanmış |
| Router'lar | ✅ Tam | CRUD + approve/reject/hard-delete + Telegram/Excel ingest + driver-statement |
| State Machine | ✅ Tam | PENDING_REVIEW → COMPLETED / REJECTED geçişleri kısıtlı |
| Enrichment Worker | ✅ Tam | SKIP LOCKED, backoff, max attempt, claim recovery |
| Outbox Worker | ✅ Tam | Per-event commit, dead-letter, claim token |
| Auth | ✅ Tam (köprü) | HS256 köprü + RS256 hedef ayarı mevcut |
| Overlap Koruması | ✅ Tam | Advisory lock + window check (driver/vehicle/trailer) |
| Kafka Broker | ✅ Tam | KafkaBroker / LogBroker / NoOpBroker ortam seçimi |
| Idempotency | ✅ Tam | SHA-256 canonical body hash, 24s TTL |
| ETag | ✅ Tam | If-Match / version optimistic lock |
| Observability | ✅ Tam | Prometheus metrikleri, JSON log, correlation ID |
| Testler | ✅ Mevcut | unit, contract, integration, worker, reliability, migration |

### 1.2 Driver Service — Telegram Alanı

`DriverModel` içinde `telegram_user_id: str | None` alanı mevcut (VARCHAR 64, nullable).
Kısıtlamalar:
- `uq_driver_telegram_user_id_live`: Benzersiz, kısmi (NULL olmayan + status ≠ CANCELLED)
- `idx_driver_telegram_user_id`: Performans indeksi

Driver service Telegram lookup (driver_id → telegram_user_id veya tersi) için public ya da internal API endpoint'i **yok**.

### 1.3 Döküman Durumu

| Döküman | Var mı | Notlar |
|---|---|---|
| `MEMORY/PLATFORM_STANDARD.md` | ✅ | Bağlayıcı, v2.0.0, güncel |
| `MEMORY/DECISIONS.md` | ✅ | ADR-001 dahil kritik kararlar kayıtlı |
| `MEMORY/PROJECT_STATE.md` | ✅ | Phase 7 - Production Ready (recovery), TASK-0047 sıradaki |
| `MEMORY/KNOWN_ISSUES.md` | ✅ | 3 açık issue |
| Trip service README | ❌ | Yok — sadece driver service'te README var |
| OpenAPI/Swagger spec | ❌ | FastAPI otomatik üretiyor (`/docs`), statik spec yok |
| Telegram Bot dökümantasyonu | ❌ | Yok — bot servisi codebase'de yok |
| PDF şablon tarifi | ❌ | Yok — henüz belirlenmemiş |

### 1.4 Kod–Döküman Uyumsuzlukları

| # | Uyumsuzluk | Gerçek Durum |
|---|---|---|
| 1 | `PROJECT_STATE.md` Next Task ID `TASK-0047` diyor ama son commit `TASK-0047` | TASK-0048 olarak güncellenmeli |
| 2 | `DECISIONS.md` Excel/import servisinin dışarı taşındığını söylüyor; trip service'te `removed_endpoints.py` 404 tombstone'ları mevcut | ✅ Uyumlu |
| 3 | Weather servisi referansı kaldırılmış; `SourceType` enum'unda yok | ✅ Uyumlu |
| 4 | Platform standard §4.2 "HS256 köprü production'da olmayacak" diyor; `config.py` production'da `PLATFORM_JWT_SECRET` varsa startup error fırlatıyor | ✅ Uyumlu |
| 5 | Driver service README "54 test" diyor; gerçek test sayısı drift etmiş olabilir (doğrulama gerekiyor) | Küçük, düşük risk |
| 6 | Trip service'te `driver_statement.py` iç router "for Telegram PDF generation" yorumunu içeriyor ama PDF üretimi yok | Bilinçli tasarım değil, eksik iş |
| 7 | `TelegramSlipIngestRequest` tam yapılandırılmış; `driver_id` zorunlu. Ama driver'ın telegram_user_id'den nasıl bulunacağı tanımlanmamış | Boşluk — Telegram bot yazmadan çözülmez |

---

## 2. Production Uygunluğu

### 2.1 Olumlu Faktörler

- **Transactional outbox**: Per-event commit, dead-letter, claim recovery — sağlam.
- **Concurrency**: Advisory lock + optimistic lock + ETag — doğru uygulanmış.
- **Auth köprüsü**: `PLATFORM_JWT_SECRET` production'da startup'ı durdururyor — bilinçsiz deploy önleniyor.
- **State machine**: Geçiş kısıtları hard-coded değil, `StateMachine[T]` generic base üzerinde.
- **Overlap koruması**: `pg_advisory_xact_lock` + window check — hafıza dışı, transaction scoped.
- **Test altyapısı**: testcontainers ile gerçek PostgreSQL, asyncio_mode=auto, contract + integration ayrımı.
- **Error format**: RFC 9457 tüm serviste tutarlı uygulanmış.

### 2.2 Production'a Geçiş İçin Gereken Maddeler

| Öncelik | Madde | Açıklama |
|---|---|---|
| 🔴 Kritik | RS256 geçişini tamamla | Identity service JWKS aktif olmalı, `PLATFORM_JWT_SECRET` kaldırılmalı |
| 🔴 Kritik | Kafka bootstrap ayarı | `TRIP_KAFKA_BOOTSTRAP_SERVERS` production değeri, SASL credentials ortam değişkenleri |
| 🟡 Yüksek | Docker Compose / K8s manifests | Tüm worker'lar (enrichment, outbox, cleanup) ayrı process olarak çalışmalı |
| 🟡 Yüksek | Location ve Fleet servisleri erişilebilir olmalı | `TRIP_FLEET_SERVICE_URL`, `TRIP_LOCATION_SERVICE_URL` production URL'leri |
| 🟡 Yüksek | DB migration chain bütünlüğü | `alembic upgrade head` tüm migration chain'i temiz uygulamalı |
| 🟠 Orta | Worker heartbeat izleme | Heartbeat tablosu var; Prometheus alert kuralları yazılmamış |
| 🟠 Orta | Dead letter yönetimi | Outbox DEAD_LETTER kayıtları için ops dashboard / alert yok |
| 🟢 Düşük | OpenAPI spec export | FastAPI `/openapi.json` endpoint üretiyor; CI'da statik export opsiyonel |

### 2.3 Şu An Production'a Götürülmeyecek Olanlar

- Telegram bot servisi (codebase'de yok)
- PDF raporu (kütüphane yok, şablon yok)
- Bu ikisi trip service'in production'a çıkmasını engellemez; bağımsız servisler olarak sonradan eklenir.

---

## 3. Telegram Sefer Fişi

### 3.1 Mevcut Altyapı

Trip service tarafında ciddi hazırlık var:

```
POST /api/v1/trips/ingest/telegram          → Tam yapılandırılmış (TelegramSlipIngestRequest)
POST /api/v1/trips/ingest/telegram-fallback → OCR başarısız olduğunda
Auth: telegram_service_auth_dependency      → SERVICE role + "telegram-service" sub
SourceType.TELEGRAM_TRIP_SLIP               → Enum'da tanımlı
EvidenceKind.SLIP_IMAGE                     → Evidence kaydı için tanımlı
telegram_message_id                         → Evidence tablosunda alan var
```

Driver service tarafında:
```
DriverModel.telegram_user_id                → VARCHAR(64), unique (kısmi), indexed
```

### 3.2 Eksikler

**Kritik boşluklar:**

| # | Eksik | Açıklama |
|---|---|---|
| 1 | **Telegram bot servisi** | Codebase'de yok. Şoförün mesajını alıp trip service'e iletecek servis yazılmalı |
| 2 | **Driver lookup by telegram_user_id** | Driver service'te `GET /internal/v1/drivers/by-telegram/{telegram_user_id}` endpoint'i yok. Bot, şoförü tanımak için buna ihtiyaç duyacak |
| 3 | **Fiş ayrıştırma / OCR** | Bot gelen görsel/metin fişi parse etmeli. Bunun için strateji belirlenmeli (OCR, regex, structured form, inline keyboard) |
| 4 | **Admin onay bildirimi** | Trip COMPLETED olduğunda şoföre Telegram bildirimi gönderilmeli. Bu outbox event'inden tetiklenebilir (trip.events.v1 consume edilir) |

### 3.3 Mimari Öneri

```
[Şoför Telegram] → [Telegram Bot Servisi (ayrı)]
                        │
                        ├── 1. driver_service GET /internal/v1/drivers/by-telegram/{tg_id}
                        │      → driver_id alır
                        │
                        ├── 2. trip_service POST /api/v1/trips/ingest/telegram
                        │      → driver_id + slip verisi → TripStatus=PENDING_REVIEW
                        │
                        └── 3. Kafka consumer (trip.events.v1)
                               → TRIP_COMPLETED event → şoföre bildirim

[Admin Panel] → trip_service POST /api/v1/trips/{id}/approve → COMPLETED
```

**Telegram bot için önerilen kütüphane:** `aiogram` (v3, async, Python 3.12 uyumlu) veya `python-telegram-bot` (v21+, asyncio).

### 3.4 Fiş Yapısı Önerisi

Bot tarafında şoförden alınacak minimal bilgi:

```
Araç plakası       : 34 ABC 123
Römorku            : 34 DEF 456 (opsiyonel)
Güzergah           : İstanbul → Ankara  (ya da route_pair_id)
Tarih/saat         : 2026-04-06 08:30 (ya da otomatik şimdiki zaman)
Brüt ağırlık (kg)  : 28500
Dara ağırlık (kg)  : 14000
```

Bu bilgilerle `TelegramSlipIngestRequest` doldurulur. OCR zorunlu değil — Telegram inline keyboard + form yanıtı daha güvenilir.

### 3.5 Driver Lookup Endpoint'i

Driver service'e eklenmesi gereken endpoint:

```
GET /internal/v1/drivers/by-telegram/{telegram_user_id}
Auth: SERVICE role ("telegram-service")
Response: { driver_id, full_name, status, is_assignable }
404: driver bulunamazsa
403: status=CANCELLED veya is_assignable=false ise
```

Bu endpoint mevcut `internal.py` router'a eklenmeli.

---

## 4. Şoför PDF Raporu

### 4.1 Mevcut Altyapı

Trip service tarafında:

```
GET /internal/v1/driver/trips
Auth: telegram_service_auth_dependency
Query params: driver_id, date_from, date_to, timezone, page, per_page
Response: JSON — { items: [...], next_cursor, total }
```

Her item'da: `trip_datetime_utc`, `trip_no`, `vehicle_plate`, `trailer_plate`, `origin_name`, `destination_name`, `net_weight_kg`, `planned_duration_s`, `status`

Bu endpoint PDF için ham veriyi sağlıyor. **PDF oluşturma yok.**

### 4.2 Eksikler

| # | Eksik | Açıklama |
|---|---|---|
| 1 | **PDF kütüphanesi** | `pyproject.toml`'da yok. Eklenmeli: `reportlab` veya `weasyprint` |
| 2 | **PDF şablonu** | Belirli bir şablon henüz yok (aşağıda öneri) |
| 3 | **PDF endpoint'i** | Ya trip service'e yeni endpoint (`GET /internal/v1/driver/trips/pdf`) eklenmeli ya da Telegram bot servisi PDF üretmeli |
| 4 | **Timezone dönüşümü** | Rapor yerel saate göre gösterilmeli — endpoint `timezone` parametresi alıyor ama PDF'de nasıl uygulanacağı tanımsız |

### 4.3 Şablon Önerisi

**Sensible default — Şoför Sefer Özet Raporu:**

```
┌─────────────────────────────────────────────────────────────┐
│  [ŞİRKET LOGOSU]           ŞOFÖR SEFER RAPORU               │
│                                                             │
│  Şoför   : Ahmet Yılmaz                                     │
│  Dönem   : 01.03.2026 – 31.03.2026 (yerel saat)             │
│  Rapor   : 2026-04-06 (oluşturma tarihi)                    │
├────┬──────────┬──────────┬─────────────┬────────────────────┤
│ #  │ Tarih    │ Araç     │ Güzergah    │ Net Ağırlık (kg)   │
├────┼──────────┼──────────┼─────────────┼────────────────────┤
│  1 │ 01.03    │ 34ABC123 │ IST → ANK   │ 14.500             │
│  2 │ 03.03    │ 34ABC123 │ ANK → İZM   │ 12.000             │
│ …  │ …        │ …        │ …           │ …                  │
├────┴──────────┴──────────┴─────────────┼────────────────────┤
│  TOPLAM SEFER SAYISI        : 12       │ TOPLAM NET : 154.000│
└────────────────────────────────────────┴────────────────────┘
│  * Yalnızca COMPLETED statüsündeki seferler dahildir.       │
│  * Bu rapor bilgi amaçlıdır, resmi belge değildir.          │
└─────────────────────────────────────────────────────────────┘
```

**Alanlar (her satır):**
- Sıra no
- Tarih (yerel, `DD.MM.YYYY`)
- Çıkış saati (`HH:MM`)
- Araç plakası
- Römorku (varsa)
- Kalkış noktası
- Varış noktası
- Net ağırlık (kg)
- Süre (saat, `planned_duration_s / 3600`)

**Footer:**
- Toplam sefer sayısı
- Toplam net ağırlık
- Uyarı: Resmi belge değildir

### 4.4 Mimari Karar: PDF Nerede Üretilmeli?

**Seçenek A — Telegram bot servisinde üret (Önerilen):**

```
Telegram Bot Servisi:
  1. GET /internal/v1/driver/trips → JSON al
  2. reportlab/weasyprint ile PDF üret
  3. PDF'i şoföre Telegram document olarak gönder
```

✅ Trip service'i sade tutar
✅ Servis sınırı ihlali yok
✅ PDF formatı değişirse trip service etkilenmez

**Seçenek B — Trip service'te endpoint:**

```
GET /internal/v1/driver/trips/pdf
Content-Type: application/pdf
```

❌ Trip service'e PDF kütüphanesi bağımlılığı girer
❌ Domain dışı sorumluluk
❌ Binary response — cache/idempotency karmaşıklaşır

**Karar: Seçenek A tercih edilmeli.** PDF üretimi Telegram bot servisinin sorumluluğu.

### 4.5 Kütüphane Önerisi

| Kütüphane | Avantaj | Dezavantaj |
|---|---|---|
| `reportlab` | Üretim kanıtlı, hızlı, küçük | API verbose, HTML şablon yok |
| `weasyprint` | HTML/CSS şablon, kolav tasarım | Sistem bağımlılıkları (pango, cairo) |
| `fpdf2` | Hafif, saf Python | Sınırlı tablo desteği |

**Öneri:** `reportlab` — en az sistem bağımlılığı, Docker'da sıfır sorun.
Şablon değişirse `Jinja2 + weasyprint` kombinasyonuna geçiş kolay.

---

## 5. Öncelikli Aksiyon Listesi

Sıralama: **production'a giden kritik yol önce**, yeni özellikler sonra.

### Faz 1 — Production'a Giden Kritik Yol (Önce Bunlar)

| # | Aksiyon | Sahip | Neden Önce |
|---|---|---|---|
| 1 | **`PROJECT_STATE.md` güncelle** — Next Task ID TASK-0048, tamamlanan task'ları kapat | — | Takip tutarlılığı, 5 dk iş |
| 2 | **RS256 geçişini tamamla** — Identity service JWKS endpoint aktif, `PLATFORM_JWT_SECRET` kaldır | identity + trip | HS256 köprüsü prod'da çalışmıyor (startup error); üretim auth bu olmadan imkansız |
| 3 | **Production ortam değişkenleri** — Kafka, DB URL, Fleet/Location URL, JWT config | DevOps | Tüm worker'lar bu değerlere bağımlı |
| 4 | **Worker process izolasyonu** — Docker Compose'da trip-api, enrichment-worker, outbox-worker, cleanup-worker ayrı container | DevOps | Worker'lar main process'le aynı container'da çalışmamalı |
| 5 | **Alembic migration doğrulama** — `alembic upgrade head` clean run, tüm servisler | — | Prod DB ilk ayağa kalkışta çalışmalı |
| 6 | **Worker heartbeat alerting** — Prometheus alert rule: heartbeat > 5 dakika yaşlıysa fire | — | Dead worker sessizce çalışmıyor olabilir |
| 7 | **Outbox dead-letter monitoring** — DEAD_LETTER sayısı alert | — | Kafka publish failure'ı sessiz kalmamalı |

### Faz 2 — Telegram Sefer Fişi

| # | Aksiyon | Bağımlılık |
|---|---|---|
| 8 | **Driver service: `GET /internal/v1/drivers/by-telegram/{tg_id}` endpoint'i** | Bağımsız; driver-service değişikliği |
| 9 | **Telegram bot servisi — scaffold** (aiogram/python-telegram-bot, ayrı servis) | Faz 1 tamamlanmış, identity auth çalışıyor |
| 10 | **Bot: driver tanıma flow** — `telegram_user_id` → driver_id lookup + kayıt yoksa yönlendirme | #8 tamamlanmış |
| 11 | **Bot: fiş giriş flow** — Araç + güzergah + ağırlık bilgisi alıp `ingest/telegram` çağrısı | #10 tamamlanmış |
| 12 | **Bot: admin onay bildirimi** — `trip.events.v1` Kafka consumer → TRIP_COMPLETED → şoföre mesaj | Kafka running |
| 13 | **Bot: hata akışları** — Geçersiz araç, güzergah bulunamadı, driver inactive senaryoları | #11 tamamlanmış |

### Faz 3 — Şoför PDF Raporu

| # | Aksiyon | Bağımlılık |
|---|---|---|
| 14 | **Şablon tasarımı netleştirilmesi** — Logo, alan listesi, dil, renk onayı | İnsan kararı gerekli |
| 15 | **Telegram bot'a PDF üretimi eklenmesi** — `reportlab` bağımlılığı + şablon kodu | #14, Faz 2 tamamlanmış |
| 16 | **Bot: `/rapor` komutu** — Tarih aralığı seçimi (inline keyboard: bu ay, geçen ay, özel) | #15 tamamlanmış |
| 17 | **PDF dosya storage kararı** — Telegram'a doğrudan document mu, S3'e upload mu? | Mimari karar |
| 18 | **Test** — Farklı sefer sayıları, uzun güzergah adları, sıfır sefer kenar durumu | #16 tamamlanmış |

### Faz 4 — Temizlik & Olgunlaştırma

| # | Aksiyon | Not |
|---|---|---|
| 19 | Trip service README oluştur | Endpoint listesi, worker açıklaması, env var listesi |
| 20 | `KNOWN_ISSUES.md` gözden geçir — ISSUE-001 ve ISSUE-003 hâlâ açık | Location lint debt ve Fleet spec bug |
| 21 | Statik OpenAPI spec export (CI'da) | `fastapi export-openapi` veya Python script |
| 22 | Driver service "54 test" sayısı doğrulama | README ile gerçek sayı sync'i |

---

## Özet Tablo

| Alan | Durum | Aciliyet |
|---|---|---|
| Trip service çekirdek kod | ✅ Production kalitesinde | — |
| Auth (RS256) | 🟡 Köprü var, geçiş bekliyor | Kritik |
| Worker process izolasyonu | 🟡 Kod hazır, infra kurulmamış | Yüksek |
| Telegram ingest endpoint'leri | ✅ Trip service'te hazır | — |
| Driver telegram_user_id alanı | ✅ Driver service'te hazır | — |
| Driver lookup by telegram ID | ❌ Endpoint yok | Orta (Faz 2 öncesi gerekli) |
| Telegram bot servisi | ❌ Codebase'de yok | Orta (Faz 2) |
| PDF üretimi | ❌ Kütüphane + şablon + kod yok | Orta (Faz 3) |
| Driver statement JSON endpoint | ✅ Trip service'te hazır | — |
| Monitoring / alerting | 🟡 Metrik var, alert yok | Yüksek (Faz 1) |
