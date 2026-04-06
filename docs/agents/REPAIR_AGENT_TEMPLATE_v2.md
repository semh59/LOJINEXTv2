# LOJINEXTv2 — Repair Agent Şablonu
> Sürüm: 2.0 | Durum: Canonical
> Yeni servis eklemek için yalnızca `LOJINEXTv2-main/MANIFEST.yaml` düzenlenir.
> Bu dosyaya dokunulmaz.

---

## PARAMETRELER

```
SERVICE_NAME = <identity-service | trip-service | location-service | driver-service | fleet-service | ...>
```

> Geçerli değerler `LOJINEXTv2-main/MANIFEST.yaml` → `services:` anahtarlarından okunur.
> Listeye hardcode edilmez; yeni servis MANIFEST'e eklendikten sonra bu şablon
> herhangi bir değişiklik olmaksızın o servis için de çalışır.

---

## REPO CONTEXT

```
Repo kökü       : LOJINEXTv2-main/
Servis kodu     : LOJINEXTv2-main/services/{{SERVICE_NAME}}/
Paylaşılan libs : LOJINEXTv2-main/packages/platform-auth/   → JWT / rol utility
                  LOJINEXTv2-main/packages/platform-common/  → StateMachine utility
Manifesto       : LOJINEXTv2-main/MANIFEST.yaml              → port, stack, owner, deps

Paylaşılan libs'e dokunma.
```

**Servis metadata (port, stack, owner, bağımlılıklar) MANIFEST'ten okunur:**

```yaml
# Örnek okuma:
MANIFEST.yaml → services.{{SERVICE_NAME}}.port
MANIFEST.yaml → services.{{SERVICE_NAME}}.stack
MANIFEST.yaml → services.{{SERVICE_NAME}}.owner_domain
MANIFEST.yaml → services.{{SERVICE_NAME}}.internal_dependencies
MANIFEST.yaml → services.{{SERVICE_NAME}}.notes
```

Bu değerleri şablona sabit yazma. MANIFEST güncel kaynak.

---

## STEP 0 — REPO MEMORY OKUMA (zorunlu; R2 kapsamı dışında)

Kod'a dokunmadan önce şu dosyaları oku:

### 1. `LOJINEXTv2-main/MEMORY/DECISIONS.md`
- Kasıtlı alınmış kararları öğren.
- Bu kararları "bug" olarak sınıflandırma.
- Değiştirmeden önce çakışma kontrolü yap.
- **Dosya yoksa:** `"MEMORY/DECISIONS.md bulunamadı — ilk çalışma, skip"` yaz ve geç.

### 2. `LOJINEXTv2-main/MEMORY/KNOWN_ISSUES.md`
- Zaten belgelenmiş sorunları öğren.
- Bunları yeniden keşfetme; patch üret ya da `"zaten açık"` olarak işaretle.
- **Dosya yoksa:** `"MEMORY/KNOWN_ISSUES.md bulunamadı — skip"` yaz ve geç.

### 3. `LOJINEXTv2-main/TASKS/{{SERVICE_NAME}}/` klasörü
Tamamlanmış task'ları tara (varsa):
- `STATE.md`        → ne yapıldı
- `CHANGED_FILES.md`→ hangi dosyalara dokunuldu
- `TEST_EVIDENCE.md`→ ne test edildi
- **Klasör yoksa:** `"TASKS/{{SERVICE_NAME}}/ bulunamadı — ilk çalışma, skip"` yaz ve geç.
- Zaten düzeltilmiş bir şeyi farklı şekilde yeniden yazma.

**Bu adım tamamlanmadan STEP 1'e geçme.**
Bulguları tek paragrafta özetle, ilerle.

---

## ROLE

Repo repair execution agent.
Analiz değil → icra.
Rapor değil → patch.

---

## SCOPE

```
Hedef  : LOJINEXTv2-main/services/{{SERVICE_NAME}}/
Amaç   : 1. Gerçek bug veya drift bul
          2. Kodu doğrudan değiştir
          3. Gerekiyorsa migration/backfill üret (down dahil)
          4. Test ekle veya düzelt
          5. Validate et
          6. Dürüst final verdict ver
```

---

## NON-NEGOTIABLE RULES

| # | Kural |
|---|-------|
| R1 | Sadece koda bakarak konuş. |
| R2 | Discovery minimum — sadece sonraki adımı açacak kadar. Uzun topoloji raporu yazma. **İstisna: STEP 0 zorunlu okuma R2 kapsamı dışındadır.** |
| R3 | "Şunu yapabilirsiniz" deme. Yap. |
| R4 | Makul varsayım yap, ilerle. Gereksiz soru sorma. |
| R5 | Minimum ama doğru değişiklik. Kozmetik refactor yok. |
| R6 | Çalışan şeyi güzellik için bozma. |
| R7 | Prod riski varsa sert düzelt. |
| R8 | Owner boundary'leri bozma. Her servis owner_domain'i MANIFEST'ten okunur. Cross-boundary bug bulursan: kendi servis tarafındaki savunmayı ekle, karşı servise dokunma. Bulguyu `REMAINING BLOCKERS`'a `[CROSS-BOUNDARY]` etiketi ile ekle. |
| R9 | Excel/Telegram entegrasyon mantığını owner domain'e taşıma. Dokunma. |
| R10 | "Mikroservis mi, monolit mi?" tartışmasına girme. Mevcut yapıyı stabilize et. |
| R11 | MEMORY/DECISIONS.md'deki kararları "bug" olarak işaretleme. Değiştirmeden önce çakışma kontrolü yap. |
| R12 | TASKS/ geçmişinde zaten düzeltilmiş bir şeyi farklı şekilde yeniden yazma. |

---

## MİMARİ KARARLAR (değiştirme, uygula)

Bu kararlar `MEMORY/DECISIONS.md`'de kilitlidir.
Agent bu kararlarla çelişen patch üretirse reddedilir.

### AUTH
- Prod ortam: RS256 / JWKS / identity-service
- Recovery bridge: `PLATFORM_JWT_SECRET` (HS256, geçici)
  - Prod'da aktifse → hard reject uygula, plaintext bırakma
  - Geçiş döneminde → warning log, blocker olarak işaretle
- Per-service local secret: bridge yoksa fallback; prod'da temizlenecek, şimdi bozma

### TRIP → FLEET → DRIVER VALIDATION
- ADR-001 kilitli: Trip, Fleet aggregation facade'ına sorar (`/internal/v1/trip-references/validate`)
- Trip doğrudan Driver'a gitmez
- Fleet, Driver'ı kendi içinde çağırır

### TRIP → LOCATION
- Location, route authority'nin sahibidir
- Route resolve: `POST /internal/v1/routes/resolve` (Location'a ait)
- Trip bu endpoint'i tüketir, route logic üretmez

### OUTBOX
- Per-event commit (tek batch commit yok)
- `PUBLISHING` state var, stale claim recovery `claim_expires_at` ile
- At-least-once delivery; downstream consumer dedup yapar

### KAFKA BROKER
```
prod env  → confluent-kafka (gerçek broker)
test env  → noop
dev env   → log
```

### LOCATION ÖZEL
- Import/export endpoint'leri kaldırıldı (410 Gone geçmişte verildi)
- Processing worker in-process değil, ayrı worker loop

---

## VALIDATE KOMUTLARI

Her priority'nin validate adımında şu komutları çalıştır (servis kökünden):

```bash
# Lint
ruff check . --select E,W,F

# Unit testler
pytest tests/unit -x -q

# Integration (ortam ayaksay varsa)
pytest tests/integration -x -q
```

> **Validate döngüsü limiti: maksimum 2 iterasyon.**
> 1. denemede fail → PATCH'e dön, düzelt, tekrar validate et.
> 2. denemede de fail → `BLOCKER` olarak işaretle, sonraki priority'ye geç.
> 3. iterasyona geçme.

---

## MİGRASYON FORMAT STANDARDI

```bash
# Yeni migration üret
alembic revision --autogenerate -m "{{SERVICE_NAME}}_<kısa_açıklama>"

# Dosya adı örneği
# 2024_001_trip_service_add_route_pair_id.py
```

Her migration dosyası:
- `upgrade()` → dolu, çalışır
- `downgrade()` → dolu, geri alır (boş bırakılamaz)
- Backfill script → idempotent (`INSERT ... ON CONFLICT DO NOTHING` veya eşdeğeri), `DRY_RUN=true` flag destekler

---

## SUCCESS / FAILURE GATES

### BAŞARI — tüm koşullar sağlanmalı

- ✓ Gerçek bug veya drift tespit edildi (dosya + satır kanıtı)
- ✓ Kod patch'i uygulandı
- ✓ Migration üretildiyse: `upgrade()` + `downgrade()` her ikisi de dolu
- ✓ Test eklendi veya düzeltildi; non-trivial (gerçek davranışı assert ediyor)
- ✓ `ruff` + `pytest` çalıştırıldı, sonuç verildi
- ✓ Validate başarısız → PATCH'e dönüldü; ya düzeltildi ya blocker işaretlendi

### BAŞARISIZLIK

- ✗ Sadece audit raporu üretmek
- ✗ Dosya listeleyip bırakmak
- ✗ Kod değiştirmeden öneri vermek
- ✗ Test çalıştırmadan "tamamlandı" demek
- ✗ Migration ekleyip `downgrade()` yazmamak
- ✗ Validate başarısız → yalnızca rapor edip geçmek
- ✗ `FIXED ISSUES` boş bırakmak →
  Ya `"Patch üretilmedi — [somut engel]"` yaz
  Ya da `"Bu priority'de gerçek defect tespit edilmedi — kanıt yok"` yaz.
  İkisi de geçerli; boş bırakmak geçersiz.

---

## PRIORITY ORDER

Sırayı bozma. Her madde: bul → patch → validate → geç.

### P1 — ASYNC / SESSION

Kontrol et; sorun varsa düzelt:
- MissingGreenlet hataları
- async session contention
- lazy loading kaynaklı runtime patlamalar
- worker session lifecycle
- long transaction / improper session scope
- background publish sırasında session misuse

Etkilenmiyor ise: `"P1 — kanıt yok, skip"` yaz ve geç.

---

### P2 — CONTRACT + DATA DRIFT

Kontrol et; sorun varsa düzelt:
- API schema ↔ DB field drift
- consumer/provider response uyumsuzluğu
- Canonical field naming tutarsızlığı
- Eski veri uyumsuzluğu → backfill gerekiyorsa üret

trip-service özelinde:
- `guzergah_id` vs `route_pair_id` kullanımı

Etkilenmiyor ise: `"P2 — kanıt yok, skip"` yaz ve geç.

---

### P3 — INTERNAL CONTRACTS

Kontrol et; sorun varsa düzelt:
- `driver_valid` / `driver_ok` tutarsızlığı
- `vehicle_valid` / `vehicle_exists` tutarsızlığı
- trailer alan tutarsızlığı
- request/response envelope standardı
- compat shim → sadeleştirme ancak pre+post test pass kanıtıyla

Etkilenmiyor ise: `"P3 — kanıt yok, skip"` yaz ve geç.

---

### P4 — AUTH / ROLE

Kontrol et; sorun varsa düzelt:
- `SUPER_ADMIN / MANAGER / OPERATOR / SERVICE` role drift
  (`platform_auth.PlatformRole` canonical'dır)
- Internal service auth drift
- Legacy auth header fallback → kaldır veya explicit deprecate
- `PLATFORM_JWT_SECRET` bridge:
  - Prod env aktifse → hard reject, plaintext bırakma
  - Geçiş → warning log, blocker işaretle
- HS256 / shared-secret kalıntısı
- RS256 / JWKS integration drift
- Prod env'de weak/plaintext/default secret riski

Etkilenmiyor ise: `"P4 — kanıt yok, skip"` yaz ve geç.

---

### P5 — OUTBOX / AUDIT / TIMELINE

Kontrol et; sorun varsa düzelt:
- Outbox state transitions (`PENDING → PUBLISHING → PUBLISHED`)
- Per-event commit uygulanmış mı?
- Stale PUBLISHING recovery: `claim_expires_at` kontrolü
- Publish success/failure update
- Retry / idempotency
- Worker heartbeat / readiness
- Audit log boşlukları (hard delete, full update)
- Timeline doğruluğu

Etkilenmiyor ise: `"P5 — kanıt yok, skip"` yaz ve geç.

---

### P6 — DB / MIGRATION / SCHEMA

Kontrol et; sorun varsa düzelt:
- Models ↔ migrations drift
- Eksik migration
- Constraint / index / default / nullability / FK sorunları
- Enum drift
- Deploy'da patlayacak schema uyumsuzluğu
- Migration format standardına uymayan dosyalar (bkz. Migrasyon Format Standardi)
- Backfill gerekiyorsa: idempotent, `DRY_RUN` flag içermeli

Üretilen her migration: `upgrade()` + `downgrade()` ikisi de dolu.

Etkilenmiyor ise: `"P6 — kanıt yok, skip"` yaz ve geç.

---

### P7 — DOCKER / COMPOSE / CI / READINESS

Kontrol et; sorun varsa düzelt:
- Docker build context hataları
- Broken Dockerfile / entrypoint
- Worker container eksikliği
- Prod compose env drift
- Plaintext secret / geçici flag prod'da aktif
- Health/ready endpoint:
  - Gerçekten DB + broker + downstream kontrolü yapıyor mu?
  - Sadece 200 döndürmüyor mu?
- CI sahte güven veriyor mu?

Başarı kriteri: `healthcheck pass` + servis 30 saniye içinde ready.

Etkilenmiyor ise: `"P7 — kanıt yok, skip"` yaz ve geç.

---

## EXECUTION LOOP

```
Her priority için:

  DISCOVER  →  minimum (sadece koda bak)
      ↓
  FIND DEFECTS  →  dosya + satır + neden kırılır
      ↓
  PATCH  →  source, test, migration, compose
      ↓
  VALIDATE  →  ruff + pytest (komutlar yukarıda)
      ↓
  Pass?  →  Sonraki priority'ye geç
  Fail?  →  PATCH'e dön, düzelt  [1. iterasyon]
             Hala fail?  →  BLOCKER işaretle, geç  [2. iterasyon max]
```

---

## DÜRÜST DİL KURALI

**YASAK:**
`muhtemelen` · `gibi görünüyor` · `olabilir` · `bence` · `teorik olarak`

**ZORUNLU:**
`doğrulandı` · `düzeltildi` · `test edildi` · `blocker kaldı` · `kanıt yok`

`"Kanıt yok"` → bu priority için skip et, geç.
Hint var ama erişilemiyor → blocker olarak işaretle.

---

## OUTPUT FORMAT

### 1. MEMORY / TASK GEÇMİŞİ ÖZETİ
- Okunan karar sayısı + kritik olanlar
- Bu servisle ilgili tamamlanmış task'lar
- Eksik dosyalar (MEMORY veya TASKS yoksa belirt)
- `"Bunları bug olarak sınıflandırmadım"` listesi

---

### 2. FIXED ISSUES

Her madde:
```
- Problem : <dosya>:<satır> — neden kırılır
- Düzeltme: ne değişti
- Dosyalar: değişen dosyalar
```

Patch yoksa zorunlu açıklama (birini seç):
```
- "Patch üretilmedi — [somut engel]"
- "Bu priority'de gerçek defect tespit edilmedi — kanıt yok"
```

---

### 3. TEST EVIDENCE
- Çalıştırılan komutlar (tam komut satırı)
- Sonuç: pass/fail sayısı
- Başarısız olanlar: sebep + aksiyon (düzeltildi mi / blocker mı?)

---

### 4. MIGRATIONS / BACKFILL
- Yeni migration: `upgrade()` + `downgrade()` var mı?
- Backfill script: idempotent mi, `DRY_RUN` flag var mı?
- Deploy sırası
- Breaking risk

---

### 5. REMAINING BLOCKERS

Sadece gerçekten kapatamadıkların.

```
Format:
  [P<n>] — <neden kapatılamadı>
  [CROSS-BOUNDARY] — <karşı servis>: <bulgu özeti> → karşı serviste kapatılması gerekir
```

---

### 6. FINAL STATUS

```
FINAL STATUS — {{SERVICE_NAME}}
─────────────────────────────────────────
Async/Session  : CLEAN | FIXED | BLOCKER
Contracts      : CLEAN | FIXED | BLOCKER
Auth           : CLEAN | FIXED | BLOCKER
Outbox/Audit   : CLEAN | FIXED | BLOCKER
Schema/Migrate : CLEAN | FIXED | BLOCKER
Docker/CI      : CLEAN | FIXED | BLOCKER
─────────────────────────────────────────
Service Status : READY | MOSTLY READY | DEGRADED | NOT READY
```

**Tanımlar:**
- `READY` → tüm priority'ler CLEAN veya FIXED, blocker yok
- `MOSTLY READY` → blocker yok, minor riskler mevcut
- `DEGRADED` → çalışıyor ama bilinen veri veya güvenlik riski var
- `NOT READY` → kritik blocker var, prod'a çıkamaz

Her `DEGRADED` veya `NOT READY` için tek satır açıklama zorunlu.

---

## FINAL COMMAND

```
{{SERVICE_NAME}} servisini şimdi gerçekten düzelt.

1. STEP 0: MEMORY ve TASKS oku (dosya yoksa belirt, geç).
2. MANIFEST.yaml'dan servis metadata'sını oku.
3. P1 → P7 sırasıyla: patch → validate → geç.
4. Output format'a göre raporla.
```
