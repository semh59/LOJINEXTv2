# LOJINEXTv2 — Derin Proje İncelemesi

**Tarih:** 2026-04-10  
**Kapsam:** 6 servis, platform altyapısı, deploy, platform-standard drift  
**Yargı:** Temel mimari kararlar doğru. Production'a giremez — 2 aktif runtime bug, 1 güvenlik açığı, çok sayıda standard drift mevcut.

---

## 1. PROJE ÖZETİ

**LOJINEXTv2**, lojistik operasyonları için tasarlanmış Python mikroservis mimarisidir. Tauri masaüstü istemcisine hizmet verecek şekilde tasarlanmıştır.

### Teknoloji Stack (Tüm servisler ortak)

| Katman | Teknoloji |
|--------|-----------|
| Runtime | Python 3.12+ |
| Framework | FastAPI (async ASGI) |
| ORM | SQLAlchemy 2.0 (async) |
| DB Driver | asyncpg |
| Veritabanı | PostgreSQL 16+ |
| Migration | Alembic (servis başına bağımsız zincir) |
| ID Üretimi | ULID (python-ulid, 26 karakter) |
| Broker | Apache Kafka (confluent-kafka) |
| Auth | RS256/JWKS (identity-service) + HS256 geçiş köprüsü |
| HTTP Client | httpx.AsyncClient |
| Test | pytest + pytest-asyncio + testcontainers |
| Lint | ruff |
| Tip Kontrolü | mypy (strict) |
| Observability | Prometheus + structured JSON logging |

### Servis Kayıt Defteri

| Servis | Port | Database | Domain |
|--------|------|----------|--------|
| trip-service | 8101 | trip_service | Seyahat yaşam döngüsü |
| fleet-service | 8102 | fleet_service | Araç/römork master data |
| location-service | 8103 | location_service | Rota/lokasyon otoritesi |
| driver-service | 8104 | driver_service | Sürücü master data |
| identity-service | 8105 | identity_service | Auth, kullanıcı, JWT |
| telegram-service | — | Yok (stateless) | Telegram bot, OCR, PDF |

### Servisler Arası İletişim (ADR-001 Locked)

```
identity-service   → JWT/JWKS → herkese
telegram-service   → driver-service (lookup)
                   → trip-service (ingest)
trip-service       → fleet-service (validate)
                   → location-service (route)
fleet-service      → driver-service (validate)
                   → trip-service (reference check)
location-service   → Mapbox (route)
                   → ORS (validate)
```

---

## 2. MİKROSERVİS İZOLASYON UYGUNLUĞU — %75

### ✅ Doğru Yapılmış

| Kriter | Durum |
|--------|-------|
| Shared DB yok — her servis kendi DB'sine bağlanıyor | ✅ |
| Servisler arası sadece HTTP + Kafka ile iletişim | ✅ |
| Python modülü cross-import yok | ✅ |
| ADR-001: Trip → Fleet → Driver zinciri | ✅ |
| Transactional outbox (tüm publishing servislerde) | ✅ |
| ULID primary key (platform geneli) | ✅ |
| FOR UPDATE SKIP LOCKED worker claim | ✅ |
| Private key AES-GCM encrypted (identity) | ✅ |
| Event-driven async worker'lar | ✅ |

### ❌ İzolasyon İhlalleri

| İhlal | Detay |
|-------|-------|
| Tek PostgreSQL container | Tüm 6 servis aynı postgres'e bağlı. Restart → platform down |
| Telegram'a gereksiz DB_URL | Stateless servis olmasına rağmen compose'da tanımlı |
| Redpanda dev-container modu | fsync kapalı, tek node. Restart = veri kaybı |
| platform-common boş | Circuit breaker, outbox relay her serviste kopyalanmış |
| HS256 geçiş köprüsü aktif | PLATFORM_JWT_SECRET henüz kaldırılmadı |

---

## 3. SERVİS BAZLI KRİTİK BULGULAR

### trip-service — 🔴 En Sorunlu Servis

**Mimari:** 1596 satır god router (`trips.py`), service/repository layer yok

| # | Sorun | Etki |
|---|-------|------|
| BUG-1 | Idempotency race — placeholder + trip aynı transaction | Duplicate trip |
| BUG-2 | State machine bypass — cancel_trip direkt status değiştiriyor | COMPLETED trip silinebilir |
| BUG-3 | Overlap check atlanıyor — planned_end_utc=None | Çift aktif trip |
| H-1 | HTTP retry yok (fleet/location) | 30 sn restart → 503 |
| H-2 | Circuit breaker yok | Cascade failure |
| H-4 | Outbox ordering garantisiz | Event sırası bozulabilir |
| M-1 | God router — 4 create endpoint tekrarı | Bakım zor |
| M-3 | Row-level auth yok | OPERATOR tüm trip'leri görebilir |

### driver-service — ⚠️ Sessiz Veri Kaybı

**Mimari:** Service layer yok, logic router'larda

| # | Sorun | Etki |
|---|-------|------|
| BUG-1 | Outbox CASCADE delete | Hard-delete → pending event'ler kaybolur |
| BUG-2 | Audit FK → SET NULL | Hard-delete → audit erişilemez |
| BUG-3 | inactivate/soft_delete commit try/except yok | Raw 500 |
| H-2 | reactivate → soft_deleted_at_utc = None | Tarih kayboluyor |
| H-4 | partition_key nullable | Ordering undefined |

### fleet-service — ✅ En Olgun Servis

**Mimari:** Doğru katmanlı (domain/services/repos/schemas/clients)

| # | Sorun | Etki |
|---|-------|------|
| BUG-1 | Circuit breaker process-safe değil | Multi-worker'da işe yaramaz |
| BUG-2 | validate_trip_compat_contract driver unavailability yakalamıyor | Driver down → trip fail |
| BUG-3 | Commit sözleşmesi belirsiz | Test tutarsızlığı |
| BUG-4 | spec_versions lazy="selectin" | N+1 yük |

### identity-service — 🔴 Güvenlik Açıkları

**Mimari:** İyi ama token_service.py 500 satır monolith

| # | Sorun | Etki |
|---|-------|------|
| BUG-1 | Login brute force yok | Tüm platforma saldırı kapısı |
| BUG-2 | Refresh token reuse tespiti yok | Token çalınma tespit edilemez |
| BUG-3 | ensure_active_signing_key race | Concurrent pod'larda çift keypair |
| H-2 | Executor graceful shutdown yok | Crypto işlemleri kesilir |
| H-3 | KEK rotation mekanizması yok | Eski key'ler açılamaz |
| H-4 | Access token revocation yok (15 dk pencere) | Deactivated user erişebilir |

### location-service — ⚠️ External Provider Riski

**Mimari:** Domain katmanı iyi ayrılmış, provider abstraction var

| # | Sorun | Etki |
|---|-------|------|
| BUG-1 | Mapbox API key URL'de plaintext | Server log'larında sızıntı |
| BUG-2 | Provider circuit breaker yok | Mapbox down → enrichment durur |
| H-1 | Provider timeout vs claim TTL validation yok | Çift processing |
| H-2 | ORS validation fallback yok | ORS down → FAILED |

### telegram-service — 🔴 Aktif Fonksiyon Bozuk

**Mimari:** Stateless, FSM tabanlı, DB yok

| # | Sorun | Etki |
|---|-------|------|
| BUG-1 | vehicle_id = truck_plate (ULID değil) | TÜM slip girişleri fail |
| BUG-2 | trip-service 5xx → jenerik hata | Kullanıcı bilgilenemiyor |
| BUG-3 | FSM state kaybolursa onay takılı | AssertionError, bot çöker |
| H-2 | Trailer ID lookup da yok | Dorse validasyonu reddedilir |

---

## 4. PLATFORM ALTYAPI SORUNLARI

### Kritik

| # | Sorun | Risk |
|---|-------|------|
| 1 | .env.example gerçek KEK değeri (git public) | Private key decrypt edilebilir |
| 2 | Redpanda dev-container (fsync kapalı) | Container restart → veri kaybı |
| 3 | AuthSettings default HS256 | Yanlışlıkla HS256 kullanma |
| 4 | JWKSKeyProvider blocking I/O (urllib sync) | Event loop 5 sn donar |

### Yüksek

| # | Sorun |
|---|-------|
| 5 | Worker healthcheck disabled |
| 6 | BaseHTTPMiddleware 4 serviste (asyncpg hang riski) |
| 7 | uv.lock Dockerfile'da kullanılmıyor |
| 8 | Dockerfile'larda HEALTHCHECK yok |

### Orta

| # | Sorun |
|---|-------|
| 9 | Tek PostgreSQL (single point of failure) |
| 10 | Nginx /v1/ tüm location_api'ye proxy |
| 11 | Nginx metrics koruması yarım |
| 12 | Telegram compose'da gereksiz DB_URL |

---

## 5. PLATFORM STANDARD DRIFT (Kod vs PLATFORM_STANDARD.md)

| Drift | Standard | Kodda Ne Var |
|-------|----------|-------------|
| BaseHTTPMiddleware | Pure ASGI zorunlu (§11.2) | 4 serviste BaseHTTPMiddleware |
| Outbox payload_json | Text zorunlu (§9.1) | Tüm servislerde JSONB |
| Event naming | `trip.created` (§9.4) | `trip.created.v1` ekstra suffix |
| Outbox claim fields | claim_token, claim_expires_at_utc zorunlu | fleet/driver/identity'de eksik |
| Row-level auth | OPERATOR kendi datasını görmeli | Trip/Fleet/Driver'da yok |
| Circuit breaker | Her downstream client'ta (§17.2) | Trip/Location/Telegram'da yok |

---

## 6. CROSS-SERVICE TUTARSIZLIKLAR

| Pattern | fleet | driver | trip | identity | location | telegram |
|---------|-------|--------|------|----------|----------|----------|
| Service layer | ✅ | ❌ | ❌ | ⚠️ | ✅ | ✅ |
| Repository layer | ✅ | ❌ | ❌ | ❌ | ✅ | n/a |
| Circuit breaker | ⚠️ | n/a | ❌ | n/a | ❌ | ❌ |
| DLQ alerting | ❌ | ❌ | ❌ | ❌ | — | — |
| Row-level auth | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Event payload | ✅ full | ⚠️ thin | 🔴 5 field | ✅ | ✅ | — |
| Idempotency | ✅ | ❌ | ✅ (race) | n/a | n/a | trip'e bırakıyor |
| Graceful shutdown | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## 7. ÖNERİLEN DÜZELTME SIRASI

### Sprint 1 — Acil (Veri bozulması / Güvenlik)
1. telegram: vehicle_id plate→ULID lookup (+ trailer)
2. trip: Idempotency ayrı transaction'a taşı
3. identity: Login rate limit (Redis)
4. deploy: .env.example KEK placeholder
5. deploy: Redpanda dev-container kaldır
6. platform-auth: AuthSettings default → RS256

### Sprint 2 — Güvenilirlik
7. identity: Refresh token family reuse detection
8. identity: ensure_active_signing_key → FOR UPDATE SKIP LOCKED
9. trip: Circuit breaker (fleet + location)
10. location: API key → Authorization header
11. location: Provider circuit breaker
12. driver: Outbox CASCADE → DEAD_LETTER
13. driver: Audit FK → plain column

### Sprint 3 — Standard Drift
14. platform-auth: JWKSKeyProvider async (httpx)
15. Tüm servisler: BaseHTTPMiddleware → pure ASGI
16. Tüm servisler: Outbox payload_json JSONB → Text
17. platform-common'a circuit_breaker, outbox_relay taşı

### Sprint 4 — Mimari İyileştirme
18. trip-service: God router → service + repository layer
19. driver-service: Service layer extraction
20. Tüm servisler: Graceful shutdown
21. Docker: Worker healthcheck, HEALTHCHECK, uv.lock

---

## 8. KORUNACAKLAR (Dokunma)

- Transactional outbox pattern
- ULID primary keys
- JWT/JWKS auth architecture
- AES-GCM KEK encryption (identity)
- Fleet 4-stage hard delete pipeline
- Advisory lock overlap detection (trip)
- ETag/row_version optimistic locking
- FOR UPDATE SKIP LOCKED worker claims
- Domain layer separation (location, fleet)
- Broker abstraction (MessageBroker ABC)