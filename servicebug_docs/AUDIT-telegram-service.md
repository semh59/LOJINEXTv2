# AUDIT: telegram-service
**Tarih:** 2025  
**Kapsam:** handlers/slip.py, clients/trip_client.py, ocr/extractor.py  
**Yargı:** Stateless, sade. 3 bug — biri kullanıcı yüzleyen sessiz hata.

---

## MİMARİ YAPI

```
telegram_service/
  handlers/
    slip.py       ← FSM: fotoğraf → OCR → onay → ingest
    statement.py  ← sürücü özeti
    common.py
  clients/
    driver_client.py   ← driver-service eligibility check
    trip_client.py     ← trip-service ingest/fallback
  ocr/
    extractor.py  ← Tesseract tabanlı field extraction
  pdf/
    generator.py  ← PDF özet
```

DB yok. Stateless. FSM state → Telegram'ın kendi FSM storage'ı.

---

## KRİTİK BULGULAR

---

### BUG-1: vehicle_id = truck_plate — Foreign Key Uyuşmazlığı

**Dosya:** `handlers/slip.py:handle_confirm` + `clients/trip_client.py:ingest_slip`

**Kanıt:**
```python
# slip.py
result = await trip_client.ingest_slip(
    driver_id=driver_id,
    vehicle_id=fields.truck_plate or "UNKNOWN",  # ← PLAKA, ID değil!
    ...
)
```

```python
# trip_client.py payload
"vehicle_id": vehicle_id,  # fleet-service'teki ULID bekleniyor
```

Trip-service `ensure_trip_references_valid` → fleet-service'e `vehicle_id` gönderir → fleet-service bu ULID'yi DB'de arar → bulamaz → **trip oluşturulamaz**.

**Etki:** Tüm Telegram slip girişleri trip-service'te `VEHICLE_NOT_FOUND` ile fail olur.

**Düzeltme:** OCR'dan plaka çık → fleet-service'e `normalized_plate` ile lookup yap → ULID döndür → o ULID'yi kullan:
```python
# driver_client.py veya fleet_client.py'e eklenecek
async def lookup_vehicle_by_plate(normalized_plate: str) -> str | None:
    resp = await client.get(f"{settings.fleet_service_url}/internal/v1/vehicles/by-plate/{normalized_plate}")
    if resp.status_code == 200:
        return resp.json()["vehicle_id"]
    return None
```

---

### BUG-2: trip-service 5xx → Sürücüye Jenerik Hata

**Dosya:** `handlers/slip.py:handle_confirm`

**Kanıt:**
```python
try:
    result = await trip_client.ingest_slip(...)
    await callback.message.edit_text("✅ Seferiniz eklendi...")
except Exception:
    logger.exception("Slip ingest failed...")
    await callback.message.edit_text("❌ Sefer eklenirken hata oluştu.")
```

`Exception` tüm hataları yakalar: validation hatası (422), network hatası, trip-service 500 — hepsi aynı mesaj.

**Etki:** Sürücü neden hata olduğunu bilmiyor. `VEHICLE_NOT_FOUND` mı? `DUPLICATE_SLIP` mı? Yönetici logdan bakıyor.

**Düzeltme:** HTTPStatusError yakala, HTTP kodu bazlı mesaj ver:
```python
except httpx.HTTPStatusError as exc:
    if exc.response.status_code == 409:
        await callback.message.edit_text("⚠️ Bu fiş zaten sisteme girilmiş.")
    elif exc.response.status_code == 422:
        await callback.message.edit_text("❌ Fiş bilgileri eksik. Yöneticinize bildirin.")
    else:
        await callback.message.edit_text("❌ Sunucu hatası. Lütfen tekrar deneyin.")
```

---

### BUG-3: FSM State Kaybolursa Onay Döngüsü Takılı Kalır

**Dosya:** `handlers/slip.py`

Sürücü fotoğraf gönderir → FSM `SlipStates.confirming`'e girer → bot restart/crash → FSM state gider → sürücü "✅ Onayla" tıklar → `state.get_data()` boş → `SlipFields.model_validate({})` → `assert fields.tare_kg is not None` → **AssertionError → unhandled exception**.

**Etki:** Bot çöker, sürücü error mesajı görmez. Yeni fotoğraf göndermek gerekiyor ama sürücü bilmiyor.

**Düzeltme:**
```python
data = await state.get_data()
if not data or "fields" not in data:
    await state.clear()
    await callback.message.edit_text("⚠️ Oturum süresi doldu. Yeni fotoğraf gönderin.")
    return
```

---

## YÜKSEK ÖNEMLİ BULGULAR

---

### H-1: OCR — Tesseract Türkçe Karakter Güvenilirliği

**Dosya:** `ocr/extractor.py`

`PIL.Image` + Tesseract tabanlı OCR. Türkçe karakterler (Ç, Ğ, İ, Ö, Ş, Ü) OCR'da sık yanlış tanınır. `_PLATE_RE` pattern'i `[A-ZÇĞİÖŞÜ]` içeriyor — doğru. Ama OCR output'ta bunlar ASCII'ye dönebilir (Ş→S, İ→I vb.). `compute_confidence()` nasıl çalışıyor görülmedi.

---

### H-2: Trailer ID Lookup Yok

Truck plate lookup bile yanlış (BUG-1) iken, dorse plakası doğrudan `normalized_trailer_plate` string olarak gönderiliyor — ULID değil. Fleet-service trailer validation'ı bunu reddeder.

---

### H-3: statement.py Pagination — Large Response

**Dosya:** `clients/trip_client.py:get_driver_statement`

```python
while True:
    resp = await client.get(..., params={"page": page, "per_page": 100})
    ...
    if page >= meta.get("total_pages", 1):
        break
    page += 1
```

Sürücünün 5 yıllık geçmişi varsa → yüzlerce sayfa → Telegram bot timeout'a düşebilir. Kullanıcıya hiç yanıt gelmez.

---

## ORTA ÖNEMLİ BULGULAR

---

### M-1: OCR Confidence Sürücü Tarafından Manipüle Edilebilir

Field correction arayüzünde:
```python
fields.ocr_confidence = fields.compute_confidence()
```

Sürücü tüm field'ları doldurunca confidence artıyor → `_is_full_slip` True → fallback yerine full ingest. Bu tasarım gereği doğru — ama sürücü yanlış bilgi girerek de full ingest tetikleyebilir.

---

## KORUNACAKLAR

| Bileşen | Durum |
|---------|-------|
| FSM state-based slip flow | ✅ iyi |
| Fallback path (düşük confidence) | ✅ iyi |
| Türkçe arayüz | ✅ iyi |
| OCR field correction | ✅ iyi |
| Driver Telegram ID lookup | ✅ iyi |

---

## DÜZELTME SIRASI

**Kritik (şu an tüm Telegram girişleri bozuk):**
1. BUG-1: `vehicle_id` → plaka ile fleet-service lookup yapıp ULID al
2. BUG-1 ek: trailer_plate için de aynısı

**Sonraki:**
3. BUG-2: HTTP hata bazlı kullanıcı mesajı
4. BUG-3: FSM state guard handle_confirm'e ekle
5. H-3: Statement pagination → tarih aralığı sınırla veya streaming mesaj
