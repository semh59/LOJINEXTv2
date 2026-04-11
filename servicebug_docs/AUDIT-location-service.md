# AUDIT: location-service
**Tarih:** 2025  
**Kapsam:** models.py, providers/, processing/pipeline.py, domain/  
**Yargı:** Domain katmanı iyi. 2 kritik external provider sorunu.

---

## MİMARİ YAPI

```
location_service/
  domain/
    classification.py  ← grade/speed hesabı
    codes.py           ← route code üretimi
    distributions.py   ← istatistiksel dağılım
    hashing.py         ← route hash
    normalization.py   ← isim normalizasyonu
  providers/
    mapbox_directions.py
    mapbox_terrain.py
    ors_validation.py
  processing/
    pipeline.py        ← ProcessingRun claim + worker
    approval.py
    bulk.py
    worker.py
  routers/             ← HTTP endpoints
  workers/             ← outbox_relay
```

Domain katmanı mevcut ve iyi ayrılmış. Provider abstraction var.

---

## KRİTİK BULGULAR

---

### BUG-1: Mapbox API Key URL Query Parameter'da

**Dosya:** `providers/mapbox_directions.py`

**Kanıt:**
```python
self.default_params = {
    "access_token": self.api_key,  # ← URL query param olarak gönderiliyor
    "geometries": "geojson",
    ...
}

response = await client.get(url, params=self.default_params, headers=headers)
# → GET https://api.mapbox.com/.../coords?access_token=sk.ey...
```

**Etki:**
- API key server access log'larında plaintext görünüyor
- Nginx/proxy log'larında full URL loglanır → key sızıyor
- Mapbox kendi log'larında bu key'i görüyor

**Düzeltme:**
```python
headers = {"Authorization": f"Bearer {self.api_key}"}
params = {k: v for k, v in self.default_params.items() if k != "access_token"}
response = await client.get(url, params=params, headers=headers)
```

---

### BUG-2: Provider'lar Arası Circuit Breaker Yok

**Dosya:** `processing/pipeline.py`, `providers/`

Mapbox down → tüm route processing durur → trip-service enrichment worker başarısız → tüm yeni trip'ler PENDING kalır.

Fleet-service `clients/trip_client.py`'de circuit breaker var. Location-service'in dış provider çağrılarında yok.

**Etki:** Mapbox API outage → yeni trip'ler sonsuza kadar enrichment queue'da birikir. Enrinchment_max_attempts'e ulaşınca FAILED → manual müdahale gerekir.

**Düzeltme:** Her provider client'a fleet-service benzeri circuit breaker ekle.

---

## YÜKSEK ÖNEMLİ BULGULAR

---

### H-1: ProcessingRun Claim TTL vs Provider Timeout

**Dosya:** `processing/pipeline.py`, `config.py`

Trip-service'deki BUG-3 ile aynı pattern. `provider_timeout_seconds` ≥ `claim_ttl_seconds` ise → worker A provider beklerken claim expire → worker B aynı run'ı claim eder → çift route hesabı. Config seviyesi validation yok.

---

### H-2: ORS Validation — Fallback Yok

`providers/ors_validation.py` route doğrulama için kullanılıyor. ORS down → validation step fail → run FAILED. Alternatif validation provider veya "skip validation" flag yok.

---

### H-3: Bulk Refresh — Rate Limiting Yok

`routers/bulk_refresh.py` endpoint'i mevcut. Büyük bulk refresh → Mapbox API rate limit'e çarpabilir. Mapbox 429 → retry storm → API ban riski.

---

## ORTA ÖNEMLİ BULGULAR

---

### M-1: Route Çakışma Kontrolü Belirsiz

`models.py`'de `RoutePair` için `pair_status` ve `PairStatus` enum var. Aktif pair'ı olan location'lar için yeni pair oluşturulduğunda çakışma kontrolü pipeline'da yapılıyor mu belirsiz. Migration `4d2b8c9e7f10_route_pair_live_uniqueness.py` var — DB constraint mevcut.

---

### M-2: LocationPoint Koordinat Precision

```python
latitude_6dp: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
longitude_6dp: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
```

6 ondalık basamak ≈ 11 cm precision. TIR lojistik için yeterli. Ama field adı `_6dp` suffix içeriyor — API response'ta bu suffix consumer'a sızıyor mu kontrol et.

---

## KORUNACAKLAR

| Bileşen | Durum |
|---------|-------|
| Domain katmanı (classification, hashing vb.) | ✅ iyi |
| Provider abstraction (Mapbox, ORS ayrı dosya) | ✅ iyi |
| ProcessingRun claim (FOR UPDATE SKIP LOCKED) | ✅ iyi |
| RouteVersion time-series (forward + reverse) | ✅ iyi |
| Outbox transactional | ✅ iyi |
| Null Island check (`0,0` koordinat yasak) | ✅ iyi |

---

## DÜZELTME SIRASI

**Kritik:**
1. BUG-1: API key → Authorization header'a taşı
2. BUG-2: Mapbox + ORS circuit breaker ekle

**Önemli:**
3. H-1: Provider timeout vs claim TTL config validator
4. H-2: ORS validation skip flag veya fallback
5. H-3: Bulk refresh → Mapbox rate limit awareness (429 backoff)
