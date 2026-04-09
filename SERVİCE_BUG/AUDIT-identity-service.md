# AUDIT: identity-service
**Tarih:** 2025  
**Kapsam:** token_service.py, crypto.py, models.py, routers/auth.py  
**Yargı:** Kriptografi doğru. 2 kritik güvenlik açığı → brute force + token reuse.

---

## MİMARİ YAPI

```
identity_service/
  token_service.py   ← tüm iş mantığı burada (god service, ~500 satır)
  crypto.py          ← AES-GCM KEK şifreleme
  jwks.py            ← RSA keypair + JWKS
  password.py        ← hash/verify (kütüphane bağlı)
  routers/
    auth.py          ← login, logout, refresh, me, service token, jwks
    admin.py         ← user management
```

Katmanlar nispeten iyi — ama `token_service.py` 500 satır monolith.

---

## KRİTİK BULGULAR

---

### BUG-1: Login Endpoint Brute Force Koruması Yok

**Dosya:** `routers/auth.py:login`

**Kanıt:**
```python
@router.post("/auth/v1/login", response_model=TokenPairResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    user = await authenticate_user(session, body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    ...
```

Rate limit yok. IP başına deneme sayısı yok. Lockout yok.

**Etki:** Saldırgan herhangi bir kullanıcı adı için saniyede yüzlerce şifre deneyebilir. Production'da tüm platforma giriş noktası bu endpoint — single point of attack.

**Düzeltme:** Redis tabanlı rate limit (örn. slowapi veya middleware):
- IP başına: 10 req/dakika
- Username başına: 5 başarısız → 15 dakika lockout

---

### BUG-2: Refresh Token Reuse Tespiti Yok

**Dosya:** `token_service.py:rotate_refresh_token`

**Kanıt:**
```python
async def rotate_refresh_token(session, raw_refresh_token):
    token_hash = _hash_token(raw_refresh_token)
    refresh_row = result.scalar_one_or_none()
    if refresh_row is None or refresh_row.revoked_at_utc is not None or ...:
        raise ValueError("Refresh token is invalid or expired.")

    refresh_row.revoked_at_utc = _now_utc()  # eski token revoke
    token_pair = await issue_token_pair(session, user)  # yeni token ver
```

Token çalınma senaryosu:
1. Kullanıcı refresh token A'ya sahip
2. Saldırgan token A'yı çalıyor
3. **Saldırgan önce** rotate → A revoke, B oluştu
4. Kullanıcı rotate dener → A revoke olmuş → 401
5. Saldırgan B ile erişmeye devam ediyor

RFC 6749 önerir: Revoked token reuse tespitinde **tüm token family'yi invalidate et**. Bu yok.

**Etki:** Refresh token çalınması tespit edilemiyor. Kullanıcı 401 alıyor, neden bilmiyor. Saldırgan aktif kalıyor.

**Düzeltme:** Token family tracking — her refresh token'a `family_id` ekle. Revoked token tekrar kullanılırsa → aynı family'deki TÜM token'ları revoke et.

---

### BUG-3: ensure_active_signing_key — Race Condition

**Dosya:** `token_service.py:ensure_active_signing_key`

**Kanıt:**
```python
async def ensure_active_signing_key(session):
    result = await session.execute(
        select(IdentitySigningKeyModel).where(IdentitySigningKeyModel.is_active.is_(True))
    )
    key = result.scalars().first()
    if key is not None:
        return key  # var, dön

    # YOK → yeni oluştur (FOR UPDATE yok!)
    private_key, public_key = generate_rsa_keypair()
    key = IdentitySigningKeyModel(...)
    session.add(key)
    await session.flush()
    return key
```

İki pod aynı anda başlarsa, ikisi de "key yok" görür → ikisi de RSA keypair üretir → birinin commit'i unique constraint'e takılır → exception. Başarılı olan pod devam eder ama bu kontrol edilmemiş concurrent write.

**Düzeltme:** `SELECT ... FOR UPDATE SKIP LOCKED` veya `INSERT ... ON CONFLICT DO NOTHING` pattern.

---

## YÜKSEK ÖNEMLİ BULGULAR

---

### H-1: Service Token Endpoint Rate Limit Yok

`/auth/v1/token/service` — saldırgan client_id/secret biliyorsa sonsuz token üretebilir. `IdentityServiceClientModel.rotated_at_utc` var ama rotation logic görülmedi.

---

### H-2: ThreadPoolExecutor Graceful Shutdown Yok

**Kanıt:**
```python
_executor = ThreadPoolExecutor(max_workers=10)  # modül seviyesi

async def _run_blocking(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, partial(func, *args, **kwargs))
```

Servis kapandığında executor.shutdown() çağrılmıyor → aktif crypto işlemleri kesilir, thread leak riski.

**Düzeltme:** `main.py` lifespan event'e:
```python
@asynccontextmanager
async def lifespan(app):
    yield
    _executor.shutdown(wait=True)
```

---

### H-3: KEK Rotation — Re-encrypt Mekanizması Yok

**Dosya:** `crypto.py`, `models.py`

`IdentitySigningKeyModel.private_key_kek_version` var — eski KEK ile şifrelenmiş key'i izlemek için. Ama `rotate_kek` endpoint veya migration job yok. KEK değişirse eski key'ler decrypt edilemez → servis çöker.

---

### H-4: JWT Access Token Revocation Yok

Kullanıcı logout olduğunda refresh token revoke oluyor ama **access token hâlâ geçerli** (expires_in kadar). SUPER_ADMIN hesabı devre dışı bırakılsa bile mevcut access token'lar çalışmaya devam eder. `decode_access_token` DB'ye bakıyor (kid lookup) ama revocation check yok.

---

## ORTA ÖNEMLİ BULGULAR

---

### M-1: Access Token Kişisel Veri İçeriyor

JWT payload'da `groups`, `permissions`, `email_masked_değil_mi` kontrol edilemedi. Eğer email veya tam isim token'da varsa → KVKK/GDPR sorunu.

---

### M-2: IdentityUserModel — soft_deleted_at_utc Yok

User deactivation sadece `is_active=False`. Deactivate tarihi, kim yaptı yok. Audit log var ama model üzerinde timestamp yok → sorgulama zorlaşır.

---

### M-3: seed_bootstrap_state Concurrent Pod Startup

**Kanıt:**
```python
user_count = await session.scalar(select(func.count()).select_from(IdentityUserModel))
if not user_count:
    # super admin oluştur
```

Birden fazla pod aynı anda başlarsa ikisi de `user_count=0` görür → ikisi de super admin oluşturmaya çalışır → biri unique constraint hatası alır. Exception handling olmadığı için pod crash riski.

---

## KORUNACAKLAR

| Bileşen | Durum |
|---------|-------|
| AES-GCM KEK şifreleme (private key plaintext DB'de değil) | ✅ iyi |
| RSA keypair rotation altyapısı (is_active + retired_at) | ✅ iyi |
| Refresh token hash (raw token DB'de değil) | ✅ iyi |
| JWKS endpoint | ✅ iyi |
| Bootstrap seeding | ✅ iyi (race condition var) |
| Permission/group model | ✅ iyi |
| Outbox + audit | ✅ iyi |
| ThreadPoolExecutor blocking crypto | ✅ doğru pattern (shutdown yok) |

---

## DÜZELTME SIRASI

**Kritik (güvenlik):**
1. BUG-1: Login rate limit → slowapi veya Redis
2. BUG-2: Refresh token family → reuse tespiti
3. BUG-3: `ensure_active_signing_key` → FOR UPDATE SKIP LOCKED

**Önemli:**
4. H-2: Executor graceful shutdown
5. H-3: KEK rotation job (migration script)
6. M-3: seed_bootstrap_state → idempotent INSERT ON CONFLICT DO NOTHING
