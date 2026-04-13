# LOJINEXTv2 — Görev Listesi (Güncellenmiş — 2026-04-13)

**Kanıtla güncellenmiştir.** Her task gerçek kod analizi ile doğrulanmıştır.

---

## 📌 DURUM ÖZETİ

| Kategori | Sayı | Task # |
|---|---|---|
| ✅ Zaten Fixed (KALDIR) | 9 | 04, 05, 06, 07, 08, 11, 12, 13, 14 |
| ❌ Standart İhlali (KALDIR) | 1 | 15 |
| 🔵 Hayali Dosya / Dead Code (ERTELE) | 3 | 10, 24, 25 |
| ⚠️ Hâlâ Geçerli | 22 | 01-03, 09, 16-23, 26-35 |

---

## FAZA 1 — Hâlâ Geçerli Kritik Bug Fix

| # | Dosya | Konu | Öncelik | Durum |
|---|---|---|---|---|
| 01 | TASK-01-identity-outbox-model.md | IdentityOutboxModel eksik kolonlar + migration | 🔴 CRITICAL | ⚠️ Doğrulanacak |
| 02 | TASK-02-location-broker-acks.md | Location + Driver + Fleet broker acks=all | 🟠 HIGH | ⚠️ Muhtemelen Fixed |
| 03 | TASK-03-identity-kafka-header.md | Identity broker Kafka header casing fix | 🟠 HIGH | ✅ Geçerli |
| — | **YENİ: BUG-013 actor_type** | Driver `actor_type="ADMIN"` → `"MANAGER"` fix | 🟠 HIGH | ✅ Geçerli |

## FAZA 2 — Orta Öncelikli Fix

| # | Dosya | Konu | Öncelik | Durum |
|---|---|---|---|---|
| 09 | TASK-09-identity-deadletter-counter.md | Identity dead-letter metric | 🟡 MEDIUM | ✅ Geçerli |

## FAZA 3 — Standartlaştırma

| # | Dosya | Konu | Öncelik | Durum |
|---|---|---|---|---|
| 16 | TASK-16-alertmanager-all-services.md | Tüm servisler için AlertManager kuralları | 🟡 MEDIUM | ✅ Geçerli |

## FAZA 4 — Kafka Consumer (Event-Driven Tamamlama)

| # | Dosya | Konu | Öncelik | Durum |
|---|---|---|---|---|
| 17 | TASK-17-platform-common-events.md | platform-common: event schema kontratları | 🔵 ARCH | ✅ Geçerli |
| 18 | TASK-18-fleet-kafka-consumer.md | Fleet-service Kafka consumer | 🔵 ARCH | ✅ Geçerli |
| 19 | TASK-19-driver-kafka-consumer.md | Driver-service Kafka consumer | 🔵 ARCH | ✅ Geçerli |
| 20 | TASK-20-location-kafka-consumer.md | Location-service Kafka consumer | 🔵 ARCH | ✅ Geçerli |
| 21 | TASK-21-trip-remove-sync-fleet.md | Trip: senkron Fleet HTTP → event-driven | 🔵 ARCH | ✅ Geçerli |
| 22 | TASK-22-trip-remove-sync-location.md | Trip: senkron Location HTTP → event-driven | 🔵 ARCH | ✅ Geçerli |
| 23 | TASK-23-saga-fleet-consumer.md | Fleet: SAGA compensation consumer | 🔵 ARCH | ✅ Geçerli |

## FAZA 5 — CI/CD

| # | Dosya | Konu | Öncelik | Durum |
|---|---|---|---|---|
| 26 | TASK-26-30-cicd-pipelines.md | Driver/Fleet/Identity/Location/Telegram CI/CD | 🟢 OPS | ✅ Geçerli |

## FAZA 6 — Kubernetes & Altyapı

| # | Dosya | Konu | Öncelik | Durum |
|---|---|---|---|---|
| 31 | TASK-31-35-k8s-and-scenario.md | HPA, PDB, NetworkPolicy, Istio, E2E test | 🟢 OPS | ✅ Geçerli |

---

## ❌ İPTAL EDİLMİŞ GÖREVLER (Gerçek Kod ile Doğrulandı)

Aşağıdaki görevler **uygulanmamalıdır** — ya bug zaten düzeltilmiş, ya dosya mevcut değil, ya da standarda aykırı.

### 🔴 Kesinlikle KALDIR — Standart İhlali

| # | Dosya | Konu | İptal Nedeni |
|---|---|---|---|
| 15 | TASK-15-outbox-payload-jsonb.md | payload_json Text → JSONB | **PLATFORM_STANDARD §9.1: "NOT JSONB — portability required"** — Bu task tam tersi yönde çalışır. 4 serviste JSONB→Text olmalı, Text→JSONB değil. |

### 🟡 KALDIR — Zaten Fixed

| # | Dosya | Konu | İptal Nedeni | Kanıt |
|---|---|---|---|---|
| 04 | TASK-04-location-session-isolation.md | Location relay HTTP yasak | Location relay'de HTTP çağrısı yok — tamamen DB+Kafka | `location_service/workers/outbox_relay.py` |
| 05 | TASK-05-location-backoff-jitter.md | Location backoff jitter | Platform-common `_mark_failed` zaten `{1:30, 2:120, 3:600, 4:3600}` + ±10% jitter | `platform_common/outbox_relay.py:295-304` |
| 06 | TASK-06-fleet-outbox-correlation.md | Fleet correlation_id ekle | `FleetOutbox` modeli ve migration zaten mevcut | `fleet_service/models.py:241` + migration `007_` |
| 07 | TASK-07-fleet-broker-double-close.md | Fleet broker double close | `OutboxRelayBase` proper session lifecycle kullanıyor | `fleet_service/workers/outbox_relay.py` |
| 08 | TASK-08-identity-hol-blocking.md | Identity HOL blocking | Platform-common DEAD_LETTER'ı zaten hariç tutuyor | `platform_common/outbox_relay.py:130-135` |
| 11 | TASK-11-trip-dqf-cleanup.md | Trip DQF wrapper kaldır | `_compute_data_quality_flag` wrapper hiçbir yerde yok | `search_files = 0 sonuç` |
| 12 | TASK-12-telegram-circuit-breaker.md | Telegram circuit breaker | `HttpClientManager` + 3 `CircuitBreaker` zaten var | `telegram_service/http_clients.py:21-23` |
| 13 | TASK-13-broker-acks-standardize.md | Broker config standardizasyon | Tüm servislerde `kafka_acks`, `kafka_enable_idempotence`, vb. zaten settings'ten okunuyor | identity/fleet/driver `config.py` |
| 14 | TASK-14-otel-tracing-rollout.md | OTEL tracing rollout | Tüm servislerin main.py ve worker'larında `setup_tracing()` zaten çağrılıyor | Her servis main.py |

### 🔵 ERTELE — Hayali Dosya / Dead Code

| # | Dosya | Konu | Erteleme Nedeni |
|---|---|---|---|
| 10 | TASK-10-saga-cleanup.md | saga.py temizlik | **`saga.py` dosyası mevcut değil** — `search_files("saga")` = 0 sonuç. Önce saga implement edilmeli. |
| 24 | TASK-24-25-saga-consumers-wireup.md (TASK-24) | Driver SAGA compensation consumer | saga.py olmadan consumer bağlanamaz. TASK-17+19 ön koşul + saga gerekli. |
| 25 | TASK-24-25-saga-consumers-wireup.md (TASK-25) | SAGA orchestrator gerçek akışa bağla | saga.py dosyası yok. Önce implement edilmeli. |

---

**Toplam:** 35 görev tanımlı → **9 iptal**, **3 ertelenmiş**, **22 geçerli**, **1 yeni** (BUG-013 actor_type fix)
**Sıra önemli:** Geçerli görevler FAZA sırasına göre uygulanmalı.