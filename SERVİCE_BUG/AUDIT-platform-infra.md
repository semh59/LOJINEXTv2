# AUDIT: Platform Altyapısı — platform_auth / platform_common / Docker / Deploy
**Tarih:** 2025  
**Kapsam:** packages/, deploy/, Dockerfile'lar, nginx, prometheus, platform standard  
**Yargı:** 2 kritik güvenlik açığı + 1 event loop blocker production'da aktif.

---

## BÖLÜM 1: platform-auth

### BUG-1 [KRİTİK — GÜVENLİK]: AuthSettings default algorithm = "HS256"

**Dosya:** `packages/platform-auth/src/platform_auth/settings.py`

```python
@dataclass(frozen=True)
class AuthSettings:
    algorithm: str = "HS256"  # ← TEHLİKELİ DEFAULT
```

Herhangi bir servis `AuthSettings(issuer="...", audience="...")` yaratırsa → RS256 değil HS256 kullanır. Test ortamlarında, yeni servis onboarding'inde, yanlışlıkla oluşturulan AuthSettings instance'larında HS256'ya düşme riski var.

**Düzeltme:**
```python
@dataclass(frozen=True)
class AuthSettings:
    algorithm: str = "RS256"  # güvenli default
```
Mevcut HS256 kullanan testler explicit `algorithm="HS256"` set etmeli.

---

### BUG-2 [KRİTİK — PERFORMANS]: JWKSKeyProvider._load_jwks event loop blocker

**Dosya:** `packages/platform-auth/src/platform_auth/key_provider.py`

```python
def _load_jwks(self) -> dict[str, Any]:
    request = urllib.request.Request(self.jwks_url, ...)
    with urllib.request.urlopen(request, timeout=5) as response:  # BLOCKING I/O
        payload = json.loads(response.read().decode("utf-8"))
```

`urllib.request.urlopen` → synchronous blocking call. FastAPI async context'te çağrılınca event loop 5 saniyeye kadar bloke olur. JWKS cache TTL 300s → her 5 dakikada bir tüm servis 5 sn donabilir.

Platform standard section 11.2: "BaseHTTPMiddleware blocks event loop" diye uyarı var ama aynı problem JWKS fetch'te mevcut.

**Düzeltme:**
```python
async def _load_jwks_async(self) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(self.jwks_url, headers={"Accept": "application/json"})
        response.raise_for_status()
        payload = response.json()
    ...
```
`JWKSKeyProvider` async hale getirilmeli. `verification_key` → `async def verification_key(...)`.
`verify_token` → `async def verify_token(...)`.
Tüm servis `auth.py` dosyaları buna göre güncellenmeli.

---

### BUG-3: _JWKS_PROVIDER_CACHE modül-level dict — concurrent race

**Dosya:** `key_provider.py`

```python
_JWKS_PROVIDER_CACHE: dict[tuple[str, int], "JWKSKeyProvider"] = {}

def build_verification_provider(settings):
    cache_key = (settings.jwks_url, settings.jwks_cache_ttl_seconds)
    provider = _JWKS_PROVIDER_CACHE.get(cache_key)
    if provider is None:
        provider = JWKSKeyProvider(...)
        _JWKS_PROVIDER_CACHE[cache_key] = provider  # race: iki coroutine aynı anda girebilir
```

Python GIL nedeniyle dict write thread-safe ama iki provider nesnesi oluşturuluyor → ikisi ayrı cache state tutuyor → çift JWKS fetch.

---

### BUG-4: ServiceTokenCache lock içinde retry — diğer coroutine'ler bloke

**Dosya:** `service_tokens.py`

```python
async with lock:
    ...
    try:
        refreshed = await self._fetch_token(...)  # 3 deneme × 5 saniye timeout = 15s
    except ServiceTokenAcquisitionError:
        ...
```

`_fetch_token` 3 deneme yapıyor, her biri 2 saniyelik timeout. Identity-service yavaşsa → lock 6+ saniye tutuluyor → tüm service token talepleri sırayla bekliyor.

**Düzeltme:** Lock sadece cache write için kullanılmalı, network call dışında tutulmalı.

---

### BUG-5: ServiceTokenCache backoff logic — başarısız backoff geçerli cache'i engelliyor

```python
if self._backoff_until.get(key, 0.0) > now and cached is None:
    raise ServiceTokenAcquisitionError("...backing off.")
```

Senaryo: Token var, expire oluyor, yenileme girişimi fail → backoff set. Sonraki istek `cached is None` (expire oldu) AND `backoff_until > now` → hata fırlatıyor. Ama token yenilenebilir olabilir. Backoff, expire sonrası ilk yenileme girişimini de engelliyor.

---

### GÖZLEM: platform_common son derece küçük

```
platform_common/
  state_machine.py  ← 31 satır
  __init__.py
```

PLATFORM_STANDARD.md section 19 "platform-common as runtime deps" diyor ama içinde sadece StateMachine var. Circuit breaker, outbox relay, middleware, http_retry — bunların hepsi her serviste ayrı ayrı kopyalanmış.

**Etki:** fleet-service'deki circuit breaker fix'i yapılırsa driver-service için ayrı yapılmalı, trip için ayrı. Hata orada da tekrar edilebilir.

---

## BÖLÜM 2: docker-compose + deploy

### BUG-6 [KRİTİK — VERI KAYBI]: Redpanda --mode dev-container

**Dosya:** `deploy/compose/production-parity/docker-compose.yml`

```yaml
redpanda:
  command:
    - --mode
    - dev-container  # ← durability devre dışı
    - --memory
    - 256M
    - --smp
    - "1"            # ← tek node, replica yok
```

`dev-container` mode: fsync devre dışı, WAL optimize edilmemiş. Container restart → **tüm Redpanda verisi kaybı**. Outbox relay bunu yeniden gönderse de PUBLISHED marklanmış event'ler tekrar gönderilmez.

**Düzeltme:**
```yaml
command:
  - redpanda
  - start
  - --smp
  - "1"
  - --memory
  - "512M"
  # dev-container KALDIRILDI — prod'da kullanma
  - --kafka-addr
  - internal://0.0.0.0:9092,external://0.0.0.0:19092
  - --advertise-kafka-addr
  - internal://redpanda:9092,external://localhost:19092
  - --set
  - redpanda.developer_mode=false
```

---

### BUG-7 [KRİTİK — GÜVENLİK]: .env.example'da gerçek KEK değeri

**Dosya:** `deploy/compose/production-parity/.env.example`

```
IDENTITY_KEY_ENCRYPTION_KEY_B64=VjJWbVptWnRaVlpWWlZaVlpWWlZaVlpWWlZaVlpWbVo=
```

Bu Base64 decode edilebilir gerçek bir değer. `example` dosyası git'te public. Bu KEK değerini kullanan herkes identity-service'in private key'lerini şifreleyemez, decrypt edebilir.

**Düzeltme:** Placeholder koy, gerçek değer koyma:
```
IDENTITY_KEY_ENCRYPTION_KEY_B64=CHANGE_ME_generate_with_openssl_rand_base64_32
```

---

### BUG-8: Tek PostgreSQL, tüm servisler — single point of failure

`postgres` container: tüm 6 servisin DB'si. Restart → platform down.
Volume `pg_data`: backup stratejisi yok.

**Prod için minimum:** Her servis kendi DB instance'ı VEYA PostgreSQL `pgbouncer` ile connection pooling + streaming replication. Docker compose'da bu mümkün değil — bunu not olarak tut.

---

### BUG-9: Worker container healthcheck disabled

```yaml
trip-enrichment:
  healthcheck:
    disable: true

driver-worker:
  healthcheck:
    disable: true
```

K8s veya Docker Swarm'a geçildiğinde → stuck worker restart edilmez. Worker heartbeat DB'de yazılıyor ama compose orchestration bunu bilmiyor.

**Düzeltme:**
```yaml
healthcheck:
  test: ["CMD-SHELL", "python -c \"
import asyncio, asyncpg, os, sys
from datetime import datetime, UTC, timedelta

async def check():
    conn = await asyncpg.connect(os.environ['TRIP_DATABASE_URL'].replace('+asyncpg',''))
    row = await conn.fetchrow(
        'SELECT recorded_at_utc FROM worker_heartbeats WHERE worker_name=$1',
        'enrichment-worker'
    )
    if not row or (datetime.now(UTC) - row['recorded_at_utc']) > timedelta(seconds=180):
        sys.exit(1)

asyncio.run(check())
\""]
  interval: 60s
  timeout: 10s
  retries: 3
```

---

### BUG-10: Telegram compose'da TELEGRAM_DATABASE_URL var — servis DB'siz

```yaml
telegram-service:
  environment:
    TELEGRAM_DATABASE_URL: postgresql+asyncpg://...  # ← telegram stateless, DB yok
```

Bu env var telegram-service'in config.py'sinde okunuyor mu belirsiz. Eğer okunmuyorsa: unused, misleading. Eğer okunuyorsa: telegram-service gizlice DB bağlantısı kuruyor.

**Aksiyon:** Telegram config.py'yi kontrol et, bu satırı kaldır.

---

## BÖLÜM 3: nginx

### BUG-11: /v1/ tüm location_api'ye proxy — çakışma riski

```nginx
location /v1/ {
    proxy_pass http://location_api;
}
```

Herhangi bir servis `/v1/` path'iyle endpoint eklerse → location_api'ye gider. Trip, fleet, driver'ın endpoint'leri `/api/v1/` prefix'i kullanıyor. Ama `/v1/` prefix'i sadece location'a açık. Yeni servis `/v1/routes/...` gibi bir endpoint eklerse: gizlice location'a gider, hata almaz.

---

### BUG-12: /admin/v1/users — path yanlış

```nginx
location /admin/v1/users {
    proxy_pass http://identity_api;
}
```

Exact match değil, prefix match. `/admin/v1/users/anything` geçer. Ama `/admin/v1/groups` geçmez → 404. Identity admin router'ının tüm path'leri `/admin/v1/` ile başlıyorsa:

```nginx
location /admin/v1/ {
    proxy_pass http://identity_api;
}
```

---

### GÖZLEM: Metrics koruması yarım

```nginx
location = /metrics {
    return 403;
}
location = /trip/metrics {
    return 403;
}
```

`/driver/metrics`, `/fleet/metrics`, `/identity/metrics` route'ları nginx'te tanımlı değil. Prometheus scrape path'i `/metrics` (servis portunda), nginx arkasında direkt erişim engelleniyor ama sadece bazı path'ler için.

---

## BÖLÜM 4: PLATFORM_STANDARD.md vs Kod

PLATFORM_STANDARD.md son derece iyi yazılmış. Gerçek kod ile arasındaki farklar:

### DRIFT-1: BaseHTTPMiddleware — 4 serviste yasak kullanılıyor

Standard section 11.2: "BaseHTTPMiddleware forbidden."
Kullanılan servisler:
- identity-service/middleware.py
- telegram-service/middleware.py
- driver-service/middleware.py
- fleet-service/middleware.py
- trip-service/middleware.py (kontrol edilmeli)

**Etki:** asyncpg connection model ile çakışma → yük altında hang riski.

---

### DRIFT-2: Outbox payload_json — JSONB vs Text

Standard section 9.1: "payload_json: Text — NOT JSONB — portability required"

Gerçek kullanım:
| Servis | payload_json tipi |
|--------|------------------|
| trip-service | JSONB |
| fleet-service | JSONB |
| driver-service | JSONB (Text olması lazım) |
| identity-service | JSONB |
| location-service | kontrol edilmedi |

Hepsi JSONB kullanıyor. Standard Text diyor. Bu bir migration gerektirir.

---

### DRIFT-3: Event naming — .v1 suffix fazladan

Standard section 9.4: `trip.created` (topic: `trip.events.v1`)
Gerçek: `trip.created.v1` event adı olarak kullanılıyor.

Bu consumer contract'ta kırılıklık — standart değişirse event adları değişmek zorunda.

---

### DRIFT-4: HTTP retry — Standard "NO retry" diyor, plan "retry ekle" dedi

Standard section 17.3: "HTTP calls at request time: NO retry. Fail fast, return 503."

Önceki audit raporlarımda tenacity retry önerisinde bulundum. Bu platform standardına **aykırı**. Platform: retry yoktur, outbox üzerinden güvenilirlik sağlanır. Bu öneriyi geri al.

---

### DRIFT-5: Section 21 Transition Backlog — açık kalan

Section 21'de listelenen açık item'lar (bazıları):

fleet-service:
- [ ] `payload_json` JSONB → Text
- [ ] Outbox: claim_token, claim_expires_at_utc, claimed_by_worker eksik
- [ ] `BaseHTTPMiddleware` → pure ASGI

driver-service:
- [ ] `retry_count` → `attempt_count`
- [ ] Outbox: aggregate_version, partition_key, claim fields eksik
- [ ] Health router yok

identity-service:
- [ ] Outbox: aggregate_version, partition_key, claim fields eksik

---

## BÖLÜM 5: Dockerfile'lar

### BUG-13: uv.lock kullanılmıyor — reproducible build yok

trip-service'de `uv.lock` var ama Dockerfile'da:
```dockerfile
RUN python -m pip install --no-cache-dir .
```

`pip install .` → `pyproject.toml`'daki `>=` sürümleri resolve eder. Build zamanına göre farklı sürümler kurulabilir. `uv.lock` ile deterministik build:
```dockerfile
RUN pip install uv && uv pip install --system --no-cache .
```

---

### BUG-14: fleet-service Dockerfile platform-common kopyalamıyor

```dockerfile
# trip-service Dockerfile
COPY packages/platform-auth /app/packages/platform-auth
COPY packages/platform-common /app/packages/platform-common  # ✅

# fleet-service Dockerfile
COPY packages/platform-auth /app/packages/platform-auth
# platform-common yok — ama fleet pyproject.toml'da da yok
```

Fleet `platform-common`'a depend etmiyor ama trip ediyor. Bu tutarlı. Problem değil ama fleet gelecekte platform-common kullanmak isterse Dockerfile güncellemek gerekecek.

---

### BUG-15: Dockerfile'larda HEALTHCHECK yönergesi yok

```dockerfile
# Her Dockerfile'da bu eksik:
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8101/health')"
```

Image-level healthcheck olmadan Docker Desktop, Portainer ve benzeri araçlar container health'i göremez.

---

## BÖLÜM 6: Prometheus / Grafana

### GÖZLEM-1: Prometheus scrape authentiation yok

```yaml
scrape_configs:
  - job_name: "trip-api"
    static_configs:
      - targets: ["trip-api:8101"]
    metrics_path: /metrics
```

/metrics endpoint'i auth gerektirmiyor (standard gereği doğru). Ama backend network izolasyonu dışında ek koruma yok. Servislerin /metrics endpoint'i kapalı ağ içinde kalmalı.

---

### GÖZLEM-2: Grafana provisioning boş mu?

```
grafana/provisioning/datasources/prometheus.yml  ← var
grafana/dashboards/trip-location-overview.json   ← var
```

Dashboard var ama içeriği okunmadı. Kontrol et — hangi metrikler izleniyor, hangisi eksik.

---

## ÖZET — Öncelik Sırası

### Hemen düzelt (güvenlik/veri kaybı):

| # | Sorun | Dosya | Risk |
|---|-------|-------|------|
| 1 | .env.example gerçek KEK | deploy/.env.example | KEK public → private key decrypt edilebilir |
| 2 | Redpanda dev-container | docker-compose.yml | Container restart → Kafka data kaybı |
| 3 | AuthSettings default HS256 | platform_auth/settings.py | Yanlış config → HS256 token kabul |

### Sonraki sprint:

| # | Sorun | Risk |
|---|-------|------|
| 4 | JWKSKeyProvider blocking I/O | Her 5 dakikada event loop donuyor |
| 5 | BaseHTTPMiddleware 4 serviste | asyncpg hang riski yük altında |
| 6 | Worker healthcheck disabled | Stuck worker tespit edilemiyor |
| 7 | Outbox JSONB → Text (drift) | Platform standard ihlali |

### Platform büyümeden:

| # | Sorun |
|---|-------|
| 8 | platform-common'a circuit_breaker, outbox_relay taşı |
| 9 | ServiceTokenCache lock scope daralt |
| 10 | Outbox event naming standardize et (`.v1` suffix kaldır) |
| 11 | uv.lock Dockerfile'a entegre et |
