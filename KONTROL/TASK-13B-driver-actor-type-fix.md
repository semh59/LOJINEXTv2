# TASK-13B — Driver `actor_type` MANAGER Mapping Fix

**Öncelik:** 🟠 P1  
**Durum:** ⚠️ Geçerli — Kod Analizi ile Doğrulandı  
**Dosya:** `services/driver-service/src/driver_service/auth.py`

---

## Bug Tanımı

`require_admin_or_manager_token()` fonksiyonunda MANAGER rolü için `actor_type = "ADMIN"` dönüyor.

```python
# Satır 137-151
async def require_admin_or_manager_token(authorization: str | None) -> AuthContext:
    claims = await _decode_claims(authorization)
    role = claims.role
    if role not in {PlatformRole.SUPER_ADMIN, PlatformRole.MANAGER}:
        raise driver_forbidden("SUPER_ADMIN or MANAGER role required.")
    actor_id = claims.sub.strip()
    if not actor_id:
        raise driver_auth_invalid("Token is missing sub.")

    actor_type = "ADMIN"                          # ← Varsayılan
    if role == PlatformRole.SUPER_ADMIN:
        actor_type = "SUPER_ADMIN"

    return AuthContext(actor_id=actor_id, role=role, actor_type=actor_type)
```

**Sorun:** MANAGER rolü için `actor_type = "ADMIN"` dönüyor. Bu audit trail'de yanlış rol kaydına yol açar.

## Düzeltme

```python
    actor_type = "MANAGER"                         # ← Doğru varsayılan
    if role == PlatformRole.SUPER_ADMIN:
        actor_type = "SUPER_ADMIN"
```

## Karşılaştırma (Aynı dosyadaki doğru implementasyon)

`require_admin_token()` (satır 117-134) bu hatayı yapmıyor:
```python
    actor_type = "ADMIN"
    if role == PlatformRole.SUPER_ADMIN:
        actor_type = "SUPER_ADMIN"
    elif role == PlatformRole.MANAGER:
        actor_type = "MANAGER"       # ← Bu doğru
```

## Etki

- Audit log'larda MANAGER kullanıcılara yanlışlıkla "ADMIN" actor_type atanır
- Compliance raporlarında rol dağılımı yanlış görünür
- 1 satırlık fix

## Kanıt

- Dosya: `services/driver-service/src/driver_service/auth.py`, satır 147-149
- Tarih: 2026-04-13 gerçek kod okuması