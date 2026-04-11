# Trip Service — Kapsamlı Test Planı

**Tarih:** 2026-04-11  
**Kapsam:** Çekirdek domain katmanı (models, service, state_machine, trip_helpers, schemas)  
**Test Edilecek Satır Sayısı:** ~2232 satır  
**Hedef Kapsam:** %90+ branch coverage  

---

## 1. Birim Testleri (Unit Tests)

### 1.1 State Machine Testleri

| Test ID | Test Adı | Amaç | Girdi | Beklenen Çıktı | Başarı Kriteri | Adımlar |
|---------|----------|------|-------|----------------|----------------|---------|
| UT-SM-001 | test_pending_review_to_completed | PENDING_REVIEW → COMPLETED geçişi | `TripStatus.PENDING_REVIEW`, `TripStatus.COMPLETED` | Exception fırlatılmaz | Geçiş başarılı | 1. TripStateMachine(PENDING_REVIEW) oluştur 2. transition_to(COMPLETED) çağır 3. current_state == COMPLETED doğrula |
| UT-SM-002 | test_pending_review_to_rejected | PENDING_REVIEW → REJECTED geçişi | `TripStatus.PENDING_REVIEW`, `TripStatus.REJECTED` | Exception fırlatılmaz | Geçiş başarılı | 1. TripStateMachine(PENDING_REVIEW) oluştur 2. transition_to(REJECTED) çağır 3. current_state == REJECTED doğrula |
| UT-SM-003 | test_pending_review_to_soft_deleted | PENDING_REVIEW → SOFT_DELETED geçişi | `TripStatus.PENDING_REVIEW`, `TripStatus.SOFT_DELETED` | Exception fırlatılmaz | Geçiş başarılı | 1. TripStateMachine(PENDING_REVIEW) oluştur 2. transition_to(SOFT_DELETED) çağır 3. current_state == SOFT_DELETED doğrula |
| UT-SM-004 | test_completed_to_soft_deleted | COMPLETED → SOFT_DELETED geçişi | `TripStatus.COMPLETED`, `TripStatus.SOFT_DELETED` | Exception fırlatılmaz | Geçiş başarılı | 1. TripStateMachine(COMPLETED) oluştur 2. transition_to(SOFT_DELETED) çağır 3. current_state == SOFT_DELETED doğrula |
| UT-SM-005 | test_soft_deleted_is_terminal | SOFT_DELETED terminal state | `TripStatus.SOFT_DELETED`, herhangi bir status | InvalidTransition hatası | Hiçbir geçişe izin verilmez | 1. TripStateMachine(SOFT_DELETED) oluştur 2. Her status için transition_to çağır 3. InvalidTransition doğrula |
| UT-SM-006 | **test_planned_state_missing** | PLANNED state geçişleri eksik | `TripStatus.PLANNED`, `TripStatus.ASSIGNED` | **InvalidTransition hatası** (BUG-003) | Mevcut durumda hata fırlatılır | 1. TripStateMachine(PLANNED) oluştur 2. transition_to(ASSIGNED) çağır 3. InvalidTransition bekle |
| UT-SM-007 | **test_assigned_state_missing** | ASSIGNED state geçişleri eksik | `TripStatus.ASSIGNED`, `TripStatus.IN_PROGRESS` | **InvalidTransition hatası** (BUG-003) | Mevcut durumda hata fırlatılır | 1. TripStateMachine(ASSIGNED) oluştur 2. transition_to(IN_PROGRESS) çağır 3. InvalidTransition bekle |
| UT-SM-008 | test_invalid_transition_completed_to_rejected | COMPLETED → REJECTED geçersiz | `TripStatus.COMPLETED`, `TripStatus.REJECTED` | InvalidTransition hatası | Geçiş reddedilir | 1. TripStateMachine(COMPLETED) oluştur 2. transition_to(REJECTED) çağır 3. InvalidTransition doğrula |
| UT-SM-009 | test_rejected_to_completed_invalid | REJECTED → COMPLETED geçersiz | `TripStatus.REJECTED`, `TripStatus.COMPLETED` | InvalidTransition hatası | Geçiş reddedilir | 1. TripStateMachine(REJECTED) oluştur 2. transition_to(COMPLETED) çağır 3. InvalidTransition doğrula |

### 1.2 Trip Helpers Testleri

| Test ID | Test Adı | Amaç | Girdi | Beklenen Çıktı | Başarı Kriteri | Adımlar |
|---------|----------|------|-------|----------------|----------------|---------|
| UT-TH-001 | test_normalize_trip_status_cancelled | Legacy CANCELLED normalizasyonu | `"CANCELLED"` | `"SOFT_DELETED"` | Legacy statü doğru normalize edilir | 1. normalize_trip_status("CANCELLED") çağır 2. "SOFT_DELETED" döndüğünü doğrula |
| UT-TH-002 | test_normalize_trip_status_current | Mevcut statü normalizasyonu | `"COMPLETED"` | `"COMPLETED"` | Normal statü değişmeden kalır | 1. normalize_trip_status("COMPLETED") çağır 2. "COMPLETED" döndüğünü doğrula |
| UT-TH-003 | test_is_deleted_trip_status_soft_deleted | Soft deleted tespiti | `"SOFT_DELETED"` | `True` | Doğru tespit | 1. is_deleted_trip_status("SOFT_DELETED") çağır 2. True döndüğünü doğrula |
| UT-TH-004 | test_is_deleted_trip_status_cancelled | Legacy cancelled tespiti | `"CANCELLED"` | `True` | Legacy statü doğru tespit | 1. is_deleted_trip_status("CANCELLED") çağır 2. True döndüğünü doğrula |
| UT-TH-005 | test_is_deleted_trip_status_completed | Active statü tespiti | `"COMPLETED"` | `False` | Aktif statü false döndürür | 1. is_deleted_trip_status("COMPLETED") çağır 2. False döndüğünü doğrula |
| UT-TH-006 | **test_latest_evidence_sorted** | Evidence sıralama doğruluğu | 3 evidence objesi (farklı created_at) | En yeni evidence | O(n log n) doğru çalışır | 1. 3 TripTripEvidence oluştur (farklı timestamps) 2. latest_evidence() çağır 3. En yeni döndüğünü doğrula |
| UT-TH-007 | **test_latest_evidence_performance** | Performance: max() vs sorted() | 1000 evidence objesi | `max()` ile aynı sonuç, daha hızlı | Performans iyileştirme fırsatı | 1. 1000 evidence oluştur 2. sorted() ile ölç 3. max() ile ölç 4. Sonuçların aynı olduğunu doğrula |
| UT-TH-008 | test_latest_evidence_empty_list | Boş evidence listesi | `trip.evidence = []` | `None` | Boş listede crash olmaz | 1. evidence attribute dict'te olmayan trip oluştur 2. latest_evidence() çağır 3. None döndüğünü doğrula |
| UT-TH-009 | test_validate_trip_weights_valid | Geçerli ağırlıklar | `tare=1000, gross=5000, net=4000` | Exception yok | Doğru ağırlıklar kabul edilir | 1. _validate_trip_weights(1000, 5000, 4000) çağır 2. Exception fırlatılmadığını doğrula |
| UT-TH-010 | test_validate_trip_weights_gross_lt_tare | Gross < Tare hatası | `tare=5000, gross=1000, net=0` | trip_validation_error | Geçersiz ağırlık yakalanır | 1. _validate_trip_weights(5000, 1000, 0) çağır 2. trip_validation_error fırlatıldığını doğrula |
| UT-TH-011 | test_validate_trip_weights_net_mismatch | Net ≠ Gross - Tare hatası | `tare=1000, gross=5000, net=3000` | trip_validation_error | Tutarsız ağırlık yakalanır | 1. _validate_trip_weights(1000, 5000, 3000) çağır 2. trip_validation_error fırlatıldığını doğrula |
| UT-TH-012 | test_validate_trip_weights_partial_null | Kısmi null ağırlıklar | `tare=None, gross=5000, net=4000` | Exception yok | Null değerler validasyonu atlar | 1. _validate_trip_weights(None, 5000, 4000) çağır 2. Exception fırlatılmadığını doğrula |
| UT-TH-013 | test_ensure_payload_size_within_limit | Normal payload | 100 KB string | Aynı string | Limit altında kabul | 1. _ensure_payload_size(100KB string, 512) çağır 2. Aynı string döndüğünü doğrula |
| UT-TH-014 | test_ensure_payload_size_exceeds_limit | Büyük payload | 600 KB string | trip_validation_error | Limit aşımı yakalanır | 1. _ensure_payload_size(600KB string, 512) çağır 2. trip_validation_error fırlatıldığını doğrula |
| UT-TH-015 | test_merged_payload_hash_deterministic | Hash determinizmi | `{"a": 1, "b": 2}` iki kez | Aynı hash | Deterministik hash | 1. _merged_payload_hash({"a":1,"b":2}) çağır 2. Sonucu kaydet 3. Tekrar çağır 4. Eşit olduğunu doğrula |
| UT-TH-016 | test_merged_payload_hash_key_order | Key sırası duyarsızlık | `{"b": 2, "a": 1}` vs `{"a": 1, "b": 2}` | Aynı hash | Key sırası fark etmez | 1. Her iki dict'i hash'le 2. Sonuçların aynı olduğunu doğrula |
| UT-TH-017 | **test_compute_data_quality_flag_high** | Manual source → HIGH | `ADMIN_MANUAL, None, False` | `"HIGH"` | Manuel trip yüksek kalite | 1. _compute_data_quality_flag("ADMIN_MANUAL", None, False) çağır 2. "HIGH" döndüğünü doğrula |
| UT-TH-018 | test_compute_data_quality_flag_ocr_high | OCR ≥0.90 + route → HIGH | `TELEGRAM, 0.95, True` | `"HIGH"` | Yüksek OCR + route = HIGH | 1. _compute_data_quality_flag("TELEGRAM_TRIP_SLIP", 0.95, True) çağır 2. "HIGH" döndüğünü doğrula |
| UT-TH-019 | test_compute_data_quality_flag_medium_ocr | OCR 0.70-0.89 → MEDIUM | `TELEGRAM, 0.75, False` | `"MEDIUM"` | Orta OCR = MEDIUM | 1. _compute_data_quality_flag("TELEGRAM_TRIP_SLIP", 0.75, False) çağır 2. "MEDIUM" döndüğünü doğrula |
| UT-TH-020 | test_compute_data_quality_flag_low | Düşük kalite | `TELEGRAM, 0.50, False` | `"LOW"` | Düşük OCR + no route = LOW | 1. _compute_data_quality_flag("TELEGRAM_TRIP_SLIP", 0.50, False) çağır 2. "LOW" döndüğünü doğrula |
| UT-TH-021 | **test_classify_manual_status_super_admin_past** | SuperAdmin geçmiş tarih | `SUPER_ADMIN auth`, geçmiş tarih | `(COMPLETED, None)` | Geçmiş trip direkt completed | 1. SuperAdmin auth context oluştur 2. Geçmiş trip_datetime ver 3. COMPLETED döndüğünü doğrula |
| UT-TH-022 | **test_classify_manual_status_super_admin_future** | SuperAdmin gelecek tarih | `SUPER_ADMIN auth`, gelecek tarih | `(PENDING_REVIEW, FUTURE_MANUAL)` | Gelecek trip pending review | 1. SuperAdmin auth context oluştur 2. Gelecek trip_datetime ver 3. PENDING_REVIEW döndüğünü doğrula |
| UT-TH-023 | test_classify_manual_status_admin_in_window | Admin 30 dk içinde | `ADMIN auth`, 15 dk önce | `(COMPLETED, None)` | Window içinde completed | 1. Admin auth context oluştur 2. 15dk önce trip_datetime ver 3. COMPLETED döndüğünü doğrula |
| UT-TH-024 | test_classify_manual_status_admin_outside_window | Admin 60 dk önce | `ADMIN auth`, 60 dk önce | `trip_invalid_date_window` hatası | Window dışı hata | 1. Admin auth context oluştur 2. 60dk önce trip_datetime ver 3. Exception doğrula |
| UT-TH-025 | test_generate_id_unique | ULID uniqueness | 1000 çağrı | 1000 farklı ID | Her ID benzersiz | 1. 1000 kez _generate_id() çağır 2. Set length == 1000 doğrula |
| UT-TH-026 | test_advisory_lock_key_stable | Advisory lock determinizmi | `"driver", "abc123"` iki kez | Aynı key | Deterministik key | 1. _advisory_lock_key("driver","abc123") çağır 2. Sonucu kaydet 3. Tekrar çağır 4. Eşit olduğunu doğrula |
| UT-TH-027 | test_advisory_lock_key_different_resources | Farklı kaynak farklı key | `"driver","1"` vs `"vehicle","1"` | Farklı key | Kaynak tipi fark eder | 1. Her iki resource için key üret 2. Farklı olduklarını doğrula |
| UT-TH-028 | **test_driver_id_none_to_empty_string** | BUG-013: None → "" dönüşümü | `TripTrip(driver_id=None)` | `driver_id=""` | **Mevcut davranış belgeleme** | 1. driver_id=None olan trip oluştur 2. trip_to_resource() çağır 3. driver_id="" döndüğünü doğrula |
| UT-TH-029 | **test_build_outbox_row_pending_string** | BUG-014: Hardcoded "PENDING" | trip_id, version, event | publish_status=="PENDING" | String vs Enum tutarsızlığı | 1. _build_outbox_row() çağır 2. publish_status değerini kontrol et |
| UT-TH-030 | **test_build_outbox_row_payload_type** | BUG-005: payload_json string/dict | dict payload | payload_json dict olmalı | Type mismatch tespiti | 1. _build_outbox_row() çağır 2. payload_json tipini kontrol et (str mi dict mi) |

### 1.3 Schema Validation Testleri

| Test ID | Test Adı | Amaç | Girdi | Beklenen Çıktı | Başarı Kriteri | Adımlar |
|---------|----------|------|-------|----------------|----------------|---------|
| UT-SC-001 | test_manual_create_valid | Geçerli manual create | Tüm zorunlu alanlar dolu | ManualCreateRequest instance | Doğru parsing | 1. Geçerli dict oluştur 2. ManualCreateRequest(**data) çağır 3. Success doğrula |
| UT-SC-002 | test_manual_create_empty_trip_no | Boş trip_no | `trip_no=""` | ValidationError | Boş string reddedilir | 1. trip_no="" olan dict oluştur 2. ValidationError bekle |
| UT-SC-003 | test_manual_create_negative_weight | Negatif ağırlık | `tare_weight_kg=-1` | ValidationError | Negatif reddedilir | 1. Negatif weight olan dict oluştur 2. ValidationError bekle |
| UT-SC-004 | test_manual_create_weight_triplet_invalid | Geçersiz ağırlık üçlüsü | `tare=5000, gross=1000, net=0` | ValidationError | gross < tare reddedilir | 1. Tutarsız weight'ler ver 2. ValidationError bekle |
| UT-SC-005 | test_manual_create_is_empty_return_rejected | is_empty_return alanı | `is_empty_return=True` | ValidationError | Manuel create'de reddedilir | 1. is_empty_return=True ver 2. ValidationError bekle |
| UT-SC-006 | test_edit_trip_timezone_without_start | Timezone tek başına güncelleme | `trip_timezone="UTC"`, `trip_start_local=None` | ValidationError | Timezone yalnız güncellenemez | 1. timezone=null olmayan, start=null olan dict ver 2. ValidationError bekle |
| UT-SC-007 | test_edit_trip_valid_partial | Kısmi güncelleme | Sadece `driver_id` | EditTripRequest instance | Partial update kabul | 1. Sadece driver_id olan dict ver 2. Success doğrula |
| UT-SC-008 | test_empty_return_valid | Geçerli empty return | Tüm alanlar dolu | EmptyReturnRequest instance | Doğru parsing | 1. Geçerli dict oluştur 2. Success doğrula |
| UT-SC-009 | test_empty_return_weight_validation | Empty return ağırlık kontrolü | `tare=1000, gross=500, net=0` | ValidationError | gross < tare reddedilir | 1. Tutarsız weight'ler ver 2. ValidationError bekle |
| UT-SC-010 | test_telegram_ingest_valid | Geçerli telegram slip | Tüm alanlar dolu | TelegramSlipIngestRequest instance | Doğru parsing | 1. Geçerli dict oluştur 2. Success doğrula |
| UT-SC-011 | test_telegram_fallback_no_timezone | Timezone'suz datetime | `message_sent_at_utc` (naive) | ValidationError | Naive datetime reddedilir | 1. tzinfo=None olan datetime ver 2. ValidationError bekle |
| UT-SC-012 | test_excel_ingest_valid | Geçerli excel import | Tüm alanlar dolu | ExcelIngestRequest instance | Doğru parsing | 1. Geçerli dict oluştur 2. Success doğrula |
| UT-SC-013 | test_excel_ingest_row_number_zero | row_number=0 | `row_number=0` | ValidationError | ge=1 constraint | 1. row_number=0 ver 2. ValidationError bekle |

---

## 2. Entegrasyon Testleri (Integration Tests)

| Test ID | Test Adı | Amaç | Girdi | Beklenen Çıktı | Başarı Kriteri | Adımlar |
|---------|----------|------|-------|----------------|----------------|---------|
| IT-001 | test_create_trip_full_lifecycle | Tam trip yaşam döngüsü | ManualCreateRequest | 201 + trip resource | Trip DB'de oluşturulur | 1. POST /trips çağır 2. 201 döndüğünü doğrula 3. DB'den trip'ı oku 4. Tüm alanların doğru olduğunu kontrol et |
| IT-002 | test_create_trip_with_idempotency | Idempotency tekrar | Aynı request + idempotency key | İkinci istekte 201 + aynı trip | Aynı trip döndürülür | 1. POST /trips (key=X) çağır → 201 2. POST /trips (key=X) tekrar çağır → 201 3. Trip ID'lerin aynı olduğunu doğrula |
| IT-003 | test_create_trip_duplicate_trip_no | Duplicate trip_no hatası | Aynı trip_no iki kez | 409 Conflict | Duplicate reddedilir | 1. POST /trips (trip_no="T001") → 201 2. POST /trips (trip_no="T001") → 409 3. Error mesajında trip_no olduğunu doğrula |
| IT-004 | **test_create_trip_integrity_error** | BUG-002: IntegrityError handling | Constraint violation | ProblemDetailResponse (409) | Güzel hata mesajı | 1. DB constraint violate eden veri gönder 2. 409 döndüğünü doğrula 3. RFC 9457 formatında olduğunu kontrol et |
| IT-005 | test_cancel_trip_full | Trip iptal akışı | Mevcut trip + cancel request | 200 + SOFT_DELETED status | Trip soft-delete olur | 1. Trip oluştur 2. DELETE /trips/{id} çağır 3. 200 döndüğünü doğrula 4. DB'de soft_deleted_at_utc dolu |
| IT-006 | test_cancel_already_cancelled | Zaten iptal edilmiş trip | SOFT_DELETED trip + cancel | 200 (idempotent) | Çift iptal hata vermez | 1. Trip iptal et 2. Tekrar iptal et 3. 200 döndüğünü doğrula |
| IT-007 | test_approve_pending_review | Onay akışı | PENDING_REVIEW trip + approve | 200 + COMPLETED status | Trip completed olur | 1. PENDING_REVIEW trip oluştur 2. POST /trips/{id}/approve çağır 3. 200 + COMPLETED döndüğünü doğrula |
| IT-008 | test_approve_completed_trip | Zaten completed trip onayı | COMPLETED trip + approve | 409 InvalidTransition | Tekrar onay reddedilir | 1. Completed trip oluştur 2. Approve çağır 3. 409 döndüğünü doğrula |
| IT-009 | test_reject_pending_review | Red akışı | PENDING_REVIEW trip + reject | 200 + REJECTED status | Trip rejected olur | 1. PENDING_REVIEW trip oluştur 2. POST /trips/{id}/reject çağır 3. 200 + REJECTED döndüğünü doğrula |
| IT-010 | test_edit_trip_basic | Temel trip düzenleme | COMPLETED trip + edit (driver_id) | 200 + yeni driver_id | Trip güncellenir | 1. Trip oluştur 2. PATCH /trips/{id} (driver_id="new") çağır 3. 200 + güncel driver_id döndüğünü doğrula |
| IT-011 | **test_edit_trip_version_increment** | BUG-001: Double version check | Trip (version=1) + edit | version=2 (NOT 3) | Version +1 artar | 1. Trip oluştur (v=1) 2. Edit çağır 3. version=2 döndüğünü doğrula |
| IT-012 | test_edit_trip_optimistic_locking | ETag conflict | Eski ETag ile edit | 412 Precondition Failed | Optimistic locking çalışır | 1. Trip oluştur (ETag al) 2. Trip güncelle (ETag değişir) 3. Eski ETag ile edit çağır 4. 412 döndüğünü doğrula |
| IT-013 | test_create_empty_return | Boş dönüş seferi | Base trip + empty return request | 201 + "-B" suffix | Empty return oluşturulur | 1. Normal trip oluştur 2. POST /trips/{id}/empty-return çağır 3. trip_no "T001-B" döndüğünü doğrula |
| IT-014 | test_create_empty_return_from_empty_return | Boş dönüş üstünden boş dönüş | Empty return trip base | 422 InvalidTransition | İkinci empty return reddedilir | 1. Empty return oluştur 2. Onun base_trip_id'si ile tekrar çağır 3. Hata döndüğünü doğrula |
| IT-015 | **test_overlap_detection_driver** | Driver overlap tespiti | Aynı driver, çakışan zaman | 409 Conflict | Overlap yakalanır | 1. Trip A oluştur (driver X, 10:00-14:00) 2. Trip B oluştur (driver X, 12:00-16:00) 3. 409 döndüğünü doğrula |
| IT-016 | test_overlap_detection_vehicle | Vehicle overlap tespiti | Aynı vehicle, çakışan zaman | 409 Conflict | Overlap yakalanır | 1. Trip A oluştur (vehicle V, 10:00-14:00) 2. Trip B oluştur (vehicle V, 12:00-16:00) 3. 409 döndüğünü doğrula |
| IT-017 | test_overlap_detection_trailer | Trailer overlap tespiti | Asame trailer, çakışan zaman | 409 Conflict | Overlap yakalanır | 1. Trip A oluştur (trailer T, 10:00-14:00) 2. Trip B oluştur (trailer T, 12:00-16:00) 3. 409 döndüğünü doğrula |
| IT-018 | test_no_overlap_different_times | Aynı kaynak, farklı zaman | Aynı driver, 10:00-12:00 ve 14:00-16:00 | Her ikisi 201 | Zaman aralığı ayrı, sorun yok | 1. Trip A oluştur 2. Trip B oluştur 3. Her ikisi başarılı |
| IT-019 | **test_cancel_audit_trail** | BUG-009: Cancel audit eksikliği | Trip cancel | Audit log entry | Audit trail oluşturulur | 1. Trip oluştur 2. Cancel et 3. trip_audit_log tablosunda kayıt kontrol et |
| IT-020 | **test_reject_audit_trail** | BUG-009: Reject audit eksikliği | Trip reject | Audit log entry | Audit trail oluşturulur | 1. PENDING_REVIEW trip oluştur 2. Reject et 3. trip_audit_log tablosunda kayıt kontrol et |

---

## 3. Performans Testleri

| Test ID | Test Adı | Amaç | Girdi | Beklenen Çıktı | Başarı Kriteri | Adımlar |
|---------|----------|------|-------|----------------|----------------|---------|
| PT-001 | test_create_trip_latency | Trip oluşturma latansı | 1000 eşzamanlı istek | < 200ms avg | SLO karşılanır | 1. k6/locust script çalıştır 2. P50 < 100ms, P99 < 500ms doğrula |
| PT-002 | test_overlap_check_latency | Overlap kontrolü performansı | 10K trip ile DB'de overlap sorgusu | < 50ms avg | Advisory lock + index performansı | 1. 10K trip seed et 2. Overlap sorgusu çalıştır 3. Latans ölç |
| PT-003 | **test_latest_evidence_benchmark** | BUG-012: sorted() vs max() | 100, 1000, 10000 evidence | max() 2x hızlı | Performans iyileştirme kanıtı | 1. N evidence oluştur 2. sorted() ile ölç 3. max() ile ölç 4. Karşılaştır |
| PT-004 | test_concurrent_create_same_driver | Concurrent driver overlap | 50 eşzamanlı istek, aynı driver | 1 başarılı, 49 conflict | Advisory lock serialize eder | 1. 50 concurrent request gönder 2. 1 x 201, 49 x 409 döndüğünü doğrula |
| PT-005 | test_idempotency_replay_latency | Idempotency replay hızı | 1000 replay isteği | < 10ms avg | Replay hızlı olmalı | 1. Trip oluştur (key ile) 2. 1000 kez replay et 3. Ortalama latans ölç |

---

## 4. Güvenlik Testleri

| Test ID | Test Adı | Amaç | Girdi | Beklenen Çıktı | Başarı Kriteri | Adımlar |
|---------|----------|------|-------|----------------|----------------|---------|
| ST-001 | test_unauthenticated_create | Kimliksiz istek | POST /trips (no auth) | 401 Unauthorized | Auth zorunlu | 1. Auth header olmadan POST /trips çağır 2. 401 döndüğünü doğrula |
| ST-002 | test_unauthorized_role_create | Yetkisiz rol | POST /trips (VIEWER role) | 403 Forbidden | RBAC çalışır | 1. VIEWER token ile POST /trips çağır 2. 403 döndüğünü doğrula |
| ST-003 | test_sql_injection_trip_no | SQL injection denemesi | `trip_no="'; DROP TABLE trip_trips;--"` | 400/422 ValidationError | Input validation çalışır | 1. Malicious trip_no gönder 2. DB tablosu hala mevcut |
| ST-004 | test_sql_injection_field_name | **BUG-011**: getattr injection | `field_name="__class__"` | Whitelist reddeder | Dynamic attribute güvenli | 1. _find_overlap(field_name="__class__") çağır 2. Exception veya whitelist reddi |
| ST-005 | test_payload_size_limit | Büyük payload | 1MB JSON evidence | 422 Validation Error | Size limit çalışır | 1. Büyük raw_payload_json gönder 2. 422 döndüğünü doğrula |
| ST-006 | test_idempotency_key_manipulation | Farklı key, aynı payload | Farklı key ile aynı request | 201 (farklı trip) | Key isolation | 1. Key=A ile trip oluştur 2. Key=B ile aynı payload gönder 3. Farklı trip ID döner |
| ST-007 | test_etag_tampering | ETag manipülasyonu | Geçersiz ETag formatı | 412 Precondition Failed | ETag validation çalışır | 1. ETag="invalid" ile edit çağır 2. 412 döndüğünü doğrula |
| ST-008 | test_hard_delete_requires_reason | Hard delete reason zorunlu | Hard delete (reason yok) | 422 ValidationError | Reason zorunlu | 1. reason="" ile hard delete çağır 2. 422 döndüğünü doğrula |
| ST-009 | test_imported_trip_driver_lock | **BUG-011 context**: Imported trip driver change | TELEGRAM trip + ADMIN driver change | 403 Forbidden | Source-locked field | 1. Telegram source trip oluştur 2. ADMIN ile driver_id değiştirmeye çalış 3. 403 döndüğünü doğrula |
| ST-010 | test_super_admin_driver_change_requires_reason | SuperAdmin driver değişimi | TELEGRAM trip + SUPER_ADMIN + no reason | 422 Change reason required | Reason zorunlu | 1. Telegram trip oluştur 2. SUPER_ADMIN ile reason olmadan driver değiştir 3. 422 döndüğünü doğrula |

---

## 5. Kenar Durum (Edge Case) Testleri

| Test ID | Test Adı | Amaç | Girdi | Beklenen Çıktı | Başarı Kriteri | Adımlar |
|---------|----------|------|-------|----------------|----------------|---------|
| EC-001 | test_create_trip_at_midnight_utc | Gece yarısı UTC | trip_start = "2024-01-01T00:00:00" | 201 | Timezone boundary | 1. Tam gece yarısı UTC'de trip oluştur 2. Başarılı olduğunu doğrula |
| EC-002 | test_create_trip_timezone_boundary | Timezone boundary (UTC+14) | `trip_timezone="Pacific/Kiritimati"` | 201 | Extreme timezone | 1. UTC+14 timezone ile trip oluştur 2. Başarılı olduğunu doğrula |
| EC-003 | test_create_trip_dst_transition | DST geçiş zamanı | DST geçiş saatinde local time | 201 veya explicit error | DST handling | 1. DST geçiş zamanında trip oluştur 2. Sonucu doğrula |
| EC-004 | test_zero_weight_trip | Sıfır ağırlık | `tare=0, gross=0, net=0` | 201 | Sıfır ağırlık geçerli | 1. Sıfır ağırlıklarla trip oluştur 2. Başarılı olduğunu doğrula |
| EC-005 | test_max_weight_trip | Maksimum integer ağırlık | `gross=2147483647` | 201 | Integer limit | 1. Max int ağırlık gönder 2. Başarılı olduğunu doğrula |
| EC-006 | test_very_long_trip_no | Uzun trip_no | 100 karakter trip_no | 201 | String limit | 1. 100 karakter trip_no gönder 2. Başarılı olduğunu doğrula |
| EC-007 | test_trip_no_exactly_100_chars | 100 karakter sınır trip_no | 100 karakter trip_no | 201 | Boundary | 1. Tam 100 karakter gönder 2. Başarılı olduğunu doğrula |
| EC-008 | test_trip_no_101_chars | 101 karakter trip_no | 101 karakter trip_no | 422 | Overflow reddedilir | 1. 101 karakter gönder 2. ValidationError bekle |
| EC-009 | test_cancel_trip_then_edit | İptal sonrası düzenleme | SOFT_DELETED trip + edit | 409 InvalidTransition | İptal sonrası edit reddedilir | 1. Trip iptal et 2. Edit çağır 3. 409 döndüğünü doğrula |
| EC-010 | test_create_empty_return_no_route_pair | Route pair'suz base trip | Base trip (route_pair_id=None) | 422 | Route pair zorunlu | 1. Route pair'suz trip oluştur 2. Empty return çağır 3. Hata döndüğünü doğrula |
| EC-011 | test_idempotency_stale_claim_cleanup | Stale claim cleanup (>60s) | Claim + 61 saniye bekleme | Claim silinir, yeni request başarılı | Stale cleanup çalışır | 1. Idempotency key ile request başlat (commit etme) 2. 61 saniye bekle 3. Aynı key ile tekrar dene 4. Başarılı olduğunu doğrula |
| EC-012 | test_concurrent_edit_same_trip | Concurrent edit yarışı | 2 eşzamanlı edit (farklı alanlar) | Biri 200, diğeri 412 | Optimistic locking | 1. Trip oluştur 2. İki concurrent edit gönder 3. 200 + 412 döndüğünü doğrula |
| EC-013 | test_empty_return_reverse_route | Reverse route doğru mu | Base trip (A→B), empty return | Empty return B→A | Route reverse doğru | 1. A→B trip oluştur 2. Empty return oluştur 3. Origin= B, Destination= A olduğunu doğrula |
| EC-014 | test_24h_fallback_planned_end | planned_end_utc=null fallback | Trip (planned_duration_s=null) | 24 saat fallback | Null duration fallback | 1. Duration'suz trip oluştur 2. planned_end_utc = start + 24h olduğunu doğrula |
| EC-015 | test_unicode_in_names | Unicode karakterler isimlerde | `origin_name="İstanbul"` | 201 | Unicode desteklenir | 1. Unicode isimlerle trip oluştur 2. Başarılı olduğunu doğrula |

---

## 6. Sistem Testleri

| Test ID | Test Adı | Amaç | Girdi | Beklenen Çıktı | Başarı Kriteri | Adımlar |
|---------|----------|------|-------|----------------|----------------|---------|
| SYST-001 | test_full_lifecycle_manual | Manuel trip tam yaşam döngüsü | Create → Edit → Approve → Timeline check | Tüm adımlar başarılı | End-to-end akış | 1. Trip oluştur 2. Düzenle 3. Onayla 4. Timeline kontrol et 5. Tüm kayıtlar DB'de |
| SYST-002 | test_full_lifecycle_telegram | Telegram slip tam yaşam döngüsü | Telegram ingest → Enrichment → Complete | Tüm adımlar başarılı | End-to-end Telegram akışı | 1. Telegram slip ingest et 2. Enrichment bekle 3. Complete olmasını doğrula |
| SYST-003 | test_cancel_recreate_flow | İptal → yeniden oluşturma | Create → Cancel → Yeni trip aynı kaynaklarla | Yeni trip başarılı | Kaynaklar serbest | 1. Trip oluştur 2. İptal et 3. Aynı kaynaklarla yeni trip oluştur 4. Başarılı olduğunu doğrula |
| SYST-004 | test_empty_return_lifecycle | Boş dönüş tam yaşam döngüsü | Create base → Create empty return → Complete | Her iki trip tamamlanır | Boş dönüş akışı | 1. Normal trip oluştur 2. Empty return oluştur 3. Her ikisini tamamla |
| SYST-005 | test_outbox_event_ordering | Event sıralama doğruluğu | 5 trip oluştur | Events created_at sıralı | FIFO ordering | 1. 5 trip peşpeşe oluştur 2. Outbox tablosunu oku 3. created_at sıralı olduğunu doğrula |

---

## 📊 Test Öncelik Matrisi

| Öncelik | Test Sayısı | Hedef |
|---------|------------|-------|
| Birim Testleri | 43 | Her BUG için en az 1 test |
| Entegrasyon | 20 | Tam yaşam döngüsü + BUG doğrulama |
| Performans | 5 | SLO doğrulama |
| Güvenlik | 10 | OWASP Top 10 |
| Kenar Durum | 15 | Boundary + edge cases |
| Sistem | 5 | End-to-end akışlar |
| **TOPLAM** | **98** | **%90+ coverage** |

---

## 🔗 BUG → Test Eşleştirmesi

| BUG ID | Test IDs | Doğrulama Türü |
|--------|----------|---------------|
| BUG-001 (Double version) | UT-TH-030, IT-011 | Birim + Entegrasyon |
| BUG-002 (IntegrityError) | IT-004 | Entegrasyon |
| BUG-003 (State machine) | UT-SM-006, UT-SM-007 | Birim |
| BUG-004 (Idempotency tx) | IT-002, EC-011 | Entegrasyon + Edge |
| BUG-005 (Outbox type) | UT-TH-030 | Birim |
| BUG-006 (Hardcoded suffix) | IT-013 | Entegrasyon |
| BUG-007 (Code repeat) | Manuel kod review | N/A |
| BUG-008 (Code repeat) | Manuel kod review | N/A |
| BUG-009 (Audit missing) | IT-019, IT-020 | Entegrasyon |
| BUG-010 (Timeline type) | UT-TH-030, IT-001 | Birim + Entegrasyon |
| BUG-011 (getattr injection) | ST-004, ST-009, ST-010 | Güvenlik |
| BUG-012 (Performance) | UT-TH-007, PT-003 | Birim + Performans |
| BUG-013 (driver_id "") | UT-TH-028 | Birim |
| BUG-014 (PENDING string) | UT-TH-029 | Birim |
| BUG-015 (Magic number) | EC-011 | Edge case |
| BUG-016 (Naming) | Manuel review | N/A |
| BUG-017 (Prefix leak) | UT-TH-009, UT-TH-010 | Birim |
| BUG-018 (Payload size) | ST-005 | Güvenlik |
| BUG-019 (Weight validation) | UT-SC-004, UT-SC-009 | Birim |
| BUG-020 (nowait=True) | PT-004 | Performans |