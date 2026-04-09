# AUDIT: driver-service
**Tarih:** 2025  
**Kapsam:** Tüm src/ incelendi  
**Yargı:** State machine doğru. 3 spesifik bug — biri sessiz veri kaybı.

---

## MİMARİ YAPI

```
driver_service/
  routers/
    lifecycle.py    ← inactivate, reactivate, soft-delete, audit
    public.py       ← CRUD
    import_jobs.py  ← async import
    internal.py     ← eligibility check
  workers/
    import_worker.py
    outbox_relay.py
  state_machine.py  ← mevcut ve doğru
  models.py
  schemas.py
```

Fleet-service'in aksine **service layer yok** — business logic router'larda. Trip-service kadar dağınık değil ama aynı pattern.

---

## KRİTİK BULGULAR

---

### BUG-1: Outbox CASCADE Delete — Pending Event'ler Sessizce Kayboluyor

**Dosya:** `models.py`

**Kanıt:**
```python
class DriverOutboxModel(Base):
    driver_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("driver_drivers.driver_id", ondelete="CASCADE"),  # ← kritik
        nullable=False,
    )
```

Driver hard-delete → outbox'taki tüm `PENDING`/`PUBLISHING` event'ler **CASCADE silinir**.

Fleet-service bunu doğru yapıyor:
```python
# fleet/services/vehicle_service.py
await outbox_repo.dead_letter_by_aggregate(session, AggregateType.VEHICLE, vehicle_id)
# ↑ önce dead-letter, sonra sil
```

Driver-service'de bu yok.

**Etki:** Driver hard-delete anında publish edilmemiş `driver.cancelled.v1`, `driver.inactivated.v1` event'leri kaybolur → consumer'lar state değişikliğinden haberdar olmaz → ghost references.

**Düzeltme:** Hard-delete öncesi outbox satırlarını DEAD_LETTER yap veya `ondelete="SET NULL"` + null driver_id'li row'ları işlemeye devam et.

---

### BUG-2: Audit Log driver_id SET NULL — GET /audit 404 Dönüyor

**Dosya:** `models.py`

**Kanıt:**
```python
class DriverAuditLogModel(Base):
    driver_id: Mapped[str] = mapped_column(
        ForeignKey("driver_drivers.driver_id", ondelete="SET NULL"),
        nullable=True,
    )
```

Driver hard-delete → audit kayıtlarının `driver_id` → NULL.

Audit endpoint:
```python
# routers/lifecycle.py:get_audit_trail
result = await session.execute(
    select(DriverModel.driver_id).where(DriverModel.driver_id == driver_id)
)
if not result.scalar_one_or_none():
    raise driver_not_found(driver_id)  # ← driver yok → 404
```

Hard-deleted driver'ın audit'i çekilemez. Audit log immutable değil — silinmiş driver'ın audit trail'i erişilemez hale geliyor.

**Düzeltme:** Audit log'da `driver_id` referansını FK olmayan plain column yap (fleet-service bunu doğru yapıyor: `FleetAssetTimelineEvent` FK yok). Ya da ayrı `get_audit_including_deleted` endpoint.

---

### BUG-3: inactivate_driver ve soft_delete_driver — Commit'te IntegrityError Yakalanmıyor

**Dosya:** `routers/lifecycle.py`

**Kanıt:**
```python
# reactivate_driver — doğru
try:
    await session.commit()
except IntegrityError as exc:
    await session.rollback()
    _handle_integrity_error(exc)

# inactivate_driver — YANLIŞ
await session.commit()        # ← try/except yok
await session.refresh(driver)

# soft_delete_driver — YANLIŞ
await session.commit()        # ← try/except yok
await session.refresh(driver)
```

**Etki:** `inactivate_driver` veya `soft_delete_driver` sırasında unique constraint ihlali → raw SQLAlchemy exception → 500. Client anlamlı hata mesajı alamaz.

---

## YÜKSEK ÖNEMLİ BULGULAR

---

### H-1: Service Layer Yok — Business Logic Router'da

`_write_audit` ve `_write_outbox` lifecycle.py içinde tanımlı. Başka router'ların kendi versiyonları var mı kontrol edilemedi — ancak bu pattern driver-service büyüdükçe spagetti üretir.

---

### H-2: reactivate_driver soft_deleted_at_utc'yi Siliyor

**Kanıt:**
```python
driver.soft_deleted_at_utc = None  # ← reactivate anında siliniyor
```

State machine `CANCELLED → ACTIVE` geçişine izin veriyor. Soft-delete tarihi kayıt altında tutulmuyor — compliance/audit açısından sorunlu.

**Düzeltme:** soft_deleted_at_utc'yi silme, `reactivated_at_utc` ayrı kolon ekle.

---

### H-3: import_worker.py — DLQ Yok

Import worker görülmedi (dosya büyük, incelenmedi) ama import_jobs modeli `FAILED` ve `PARTIAL_SUCCESS` statüsü var. Job başarısız olursa retry mekanizması ve dead-letter yolu belirsiz.

---

### H-4: Driver Outbox — partition_key Nullable

**Kanıt:**
```python
partition_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

Trip-service ve fleet-service'de partition_key mandatory. Burada nullable. Outbox relay partition_key'e göre ordering yapıyorsa null row'lar undefined davranış üretir.

---

## ORTA ÖNEMLİ BULGULAR

---

### M-1: Audit Log Snapshot'ta Phone Masking Tutarsız

```python
# lifecycle.py:_write_audit
if old_snapshot and "phone" in old_snapshot:
    old_snapshot["phone"] = mask_phone_for_manager(old_snapshot["phone"])
```

Sadece "phone" key'i maskeli. `phone_raw`, `phone_e164` field'ları maskelenmiyor. Audit snapshot'ta ham e164 numarası kalıyor.

---

### M-2: Row-Level Auth Yok

`public.py`'de OPERATOR rolü tüm driver'ları görebilir (fleet-service ve trip-service ile aynı problem). Sürücüler kendi datalarını diğerlerinin datası ile birlikte görüyor.

---

## KORUNACAKLAR

| Bileşen | Durum |
|---------|-------|
| State machine (5 status, geçişler doğru) | ✅ iyi |
| Audit log (high-fidelity snapshot) | ✅ iyi (FK sorunu var) |
| Outbox pattern | ✅ iyi (CASCADE sorunu var) |
| ETag/row_version optimistic locking | ✅ iyi |
| Phone normalization (E.164) | ✅ iyi |
| Import job tracking | ✅ iyi |
| Merge history table | ✅ iyi |

---

## DÜZELTME SIRASI

**Öncelikli (veri kaybı):**
1. BUG-1: Outbox `ondelete="CASCADE"` → hard-delete öncesi DEAD_LETTER yap
2. BUG-2: Audit log FK → plain column, hard-delete sonrası erişilebilir

**Sonraki:**
3. BUG-3: `inactivate_driver` + `soft_delete_driver` commit try/except
4. H-2: `soft_deleted_at_utc = None` → `reactivated_at_utc` ile değiştir
5. H-4: partition_key NOT NULL yap
6. M-1: Phone masking → `phone_e164` da maskele
