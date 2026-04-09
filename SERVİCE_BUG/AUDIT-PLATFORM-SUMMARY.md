# AUDIT: Platform Özeti — LOJINEXTv2
**Tarih:** 2025  
**Kapsam:** 6 servis, tüm src/ kanıt temelli incelendi  
**Yargı:** Platform production'a giremez — 2 aktif runtime bug, 1 güvenlik açığı.

---

## CROSS-SERVICE HARİTASI

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

Shared DB yok. Servisler sadece API/event üzerinden konuşuyor. ✅

---

## ACİL DÜZELTMELER (production'a gitmeden)

Bunlar şu an aktif veri bozuyor veya tüm girişleri engelliyor:

---

**#1 — telegram-service: vehicle_id = truck_plate**
Tüm Telegram slip girişleri `VEHICLE_NOT_FOUND` ile fail oluyor.
`handlers/slip.py` → plaka ile fleet-service lookup → ULID al.

---

**#2 — trip-service: Idempotency race condition**
IntegrityError + retry → duplicate trip.
`trip_helpers.py:_check_idempotency_key` → ayrı transaction.

---

**#3 — identity-service: Login brute force koruması yok**
`/auth/v1/login` rate limit yok → tüm platforma saldırı kapısı.
Redis rate limit middleware ekle.

---

## SERVİS BAZLI DURUM

| Servis | Mimari | Kritik Bug | Güvenilirlik | Güvenlik |
|--------|--------|------------|--------------|----------|
| fleet-service | ✅ Layered | ⚠️ CB scope | ⚠️ Driver CB bypass | ✅ |
| driver-service | ⚠️ No service layer | 🔴 Outbox CASCADE | ⚠️ Audit 404 | ✅ |
| identity-service | ✅ OK | ⚠️ SM race | 🔴 No rate limit | 🔴 Brute force |
| location-service | ✅ Domain layer | 🔴 API key URL'de | ⚠️ No CB | ✅ |
| telegram-service | ✅ Stateless | 🔴 Wrong vehicle_id | ⚠️ No retry | ✅ |
| trip-service | 🔴 God router | 🔴 Idempotency race | 🔴 No CB/retry | ⚠️ No row isolation |

---

## PLATFORM GENELİ EKSİKLER

Servis bazlı değil, platform geneli — hiçbirinde yok:

**Rate limiting:** Sadece identity login sorunu değil. trip-service ingest, fleet create — hepsinde yok.

**Connection pool config:** SQLAlchemy default 5 connection. Prod'da tüm servisler yük altında tıkanır.

**Graceful shutdown:** Hiçbir serviste signal handler yok. Deploy sırasında in-flight request kesilir.

**Alert:** Dead-letter, enrichment failure, outbox lag — hiçbirinde metric threshold → alert bağlantısı yok.

**Migration rollback plan:** Her serviste `final_forensic_parity` migration var. Kötü migration = rollback = manuel.

---

## CROSS-SERVICE TUTARSIZLIKLAR

| Pattern | fleet | driver | trip | identity | location | telegram |
|---------|-------|--------|------|----------|----------|----------|
| Circuit breaker | ✅ (scope yanlış) | n/a | ❌ | n/a | ❌ | ❌ |
| HTTP retry | ❌ | n/a | ❌ | n/a | ✅ Mapbox | ❌ |
| DLQ alert | ❌ | ❌ | ❌ | ❌ | — | — |
| Row-level auth | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Event payload snapshot | ✅ full | ⚠️ thin | 🔴 5 field | ✅ | ✅ | — |
| Idempotency | ✅ | ❌ | ✅ (race var) | n/a | n/a | trip-service'e bırakıyor |

---

## SALDO

**Doğru yapılmış (koru):**
- Transactional outbox — hepsi var
- FOR UPDATE SKIP LOCKED worker claim — hepsi var
- ULID primary key — hepsi var
- JWT/JWKS auth — doğru kurulmuş
- Private key AES-GCM encrypted — identity güçlü
- fleet-service 4-stage hard delete — model al

**Düzelt (rewrite değil):**
- trip-service: idempotency race + state machine bypass + god router
- driver-service: outbox CASCADE + audit FK
- identity-service: brute force + token reuse
- location-service: API key URL'den header'a
- telegram-service: vehicle_id lookup

**Sıfırdan yazılacak yok** — tüm servisler kurtarılabilir.

---

## ÖNERİLEN SPRINT PLANI

**Sprint 1 — Acil (bu hafta):**
- telegram: vehicle_id plate→ULID lookup
- trip: idempotency ayrı transaction
- identity: login rate limit

**Sprint 2 — Güvenilirlik:**
- trip: HTTP retry + circuit breaker
- location: API key header + CB
- driver: outbox CASCADE fix + audit FK fix
- identity: refresh token family

**Sprint 3 — Maintainability:**
- trip: service layer + repository extraction
- driver: service layer extraction
- platform: connection pool config (tüm servisler)

**Sprint 4 — Operasyon:**
- platform: graceful shutdown (tüm servisler)
- platform: DLQ alerting (tüm servisler)
- platform: row-level auth (trip + fleet + driver)
- platform: event payload standardization
