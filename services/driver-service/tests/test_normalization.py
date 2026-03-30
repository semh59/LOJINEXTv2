"""Unit tests for normalization module — spec Appendix A algorithms."""

from driver_service.normalization import (
    build_full_name_search_key,
    derive_lifecycle_state,
    etag_from_row_version,
    mask_phone_for_manager,
    normalize_phone,
    parse_if_match,
)

# ---------------------------------------------------------------------------
# A.1  build_full_name_search_key — Turkish normalization
# ---------------------------------------------------------------------------


class TestBuildFullNameSearchKey:
    def test_basic_ascii(self):
        assert build_full_name_search_key("John Doe") == "john doe"

    def test_turkish_uppercase_i(self):
        """Turkish İ must become 'i', not 'i̇'."""
        result = build_full_name_search_key("İBRAHİM")
        assert "̇" not in result  # no combining dot above
        assert result == "ibrahim"

    def test_turkish_lowercase_dotless_i(self):
        """Turkish ı (dotless i) must become 'i'."""
        result = build_full_name_search_key("IĞDIR")
        assert result == "igdir"

    def test_turkish_special_chars(self):
        """All Turkish special letters are transliterated."""
        result = build_full_name_search_key("Çağrı Güneş Öztürk Şahin Ünal")
        assert result == "cagri gunes ozturk sahin unal"

    def test_whitespace_collapse(self):
        result = build_full_name_search_key("  Ali   Veli   ")
        assert result == "ali veli"

    def test_empty_after_strip(self):
        result = build_full_name_search_key("   ")
        assert result == ""

    def test_mixed_case_turkish(self):
        result = build_full_name_search_key("Mehmet YILMAZ")
        assert result == "mehmet yilmaz"


# ---------------------------------------------------------------------------
# A.2  normalize_phone — E.164 normalization
# ---------------------------------------------------------------------------


class TestNormalizePhone:
    def test_valid_turkish_number(self):
        result = normalize_phone("5551234567")
        assert result.status.value == "NORMALIZED"
        assert result.phone_e164 == "+905551234567"
        assert result.phone_raw == "5551234567"

    def test_valid_with_country_code(self):
        result = normalize_phone("+905551234567")
        assert result.status.value == "NORMALIZED"
        assert result.phone_e164 == "+905551234567"

    def test_valid_with_zero_prefix(self):
        result = normalize_phone("05551234567")
        assert result.status.value == "NORMALIZED"
        assert result.phone_e164 == "+905551234567"

    def test_invalid_phone(self):
        result = normalize_phone("123")
        assert result.status.value in {"INVALID", "RAW_UNKNOWN"}

    def test_null_phone_not_allowed(self):
        result = normalize_phone(None)
        assert result.status.value == "MISSING"
        assert result.phone_e164 is None

    def test_null_phone_allowed_for_import(self):
        result = normalize_phone(None, allow_missing=True)
        assert result.status.value == "MISSING"
        assert result.phone_e164 is None

    def test_empty_string(self):
        result = normalize_phone("")
        assert result.status.value == "MISSING"

    def test_totally_invalid_format(self):
        result = normalize_phone("not-a-phone")
        assert result.status.value == "RAW_UNKNOWN"
        assert result.phone_raw == "not-a-phone"

    def test_explicit_region_override(self):
        result = normalize_phone("2025551234", default_region="US")
        assert result.status.value == "NORMALIZED"
        assert result.phone_e164 == "+12025551234"


# ---------------------------------------------------------------------------
# Phone masking (BR-17)
# ---------------------------------------------------------------------------


class TestMaskPhoneForManager:
    def test_standard_turkish_number(self):
        result = mask_phone_for_manager("+905551234567")
        assert result == "+9055******67"
        assert len(result) == len("+905551234567")

    def test_none_returns_none(self):
        assert mask_phone_for_manager(None) is None

    def test_short_number(self):
        result = mask_phone_for_manager("+1234")
        assert result == "*****"


# ---------------------------------------------------------------------------
# lifecycle_state derivation
# ---------------------------------------------------------------------------


class TestDeriveLifecycleState:
    def test_active_no_soft_delete(self):
        assert derive_lifecycle_state("ACTIVE", None) == "ACTIVE"

    def test_inactive_no_soft_delete(self):
        assert derive_lifecycle_state("INACTIVE", None) == "INACTIVE"

    def test_active_with_soft_delete(self):
        """Soft delete takes priority over status."""
        from datetime import datetime, timezone

        assert derive_lifecycle_state("ACTIVE", datetime.now(timezone.utc)) == "SOFT_DELETED"

    def test_inactive_with_soft_delete(self):
        from datetime import datetime, timezone

        assert derive_lifecycle_state("INACTIVE", datetime.now(timezone.utc)) == "SOFT_DELETED"


# ---------------------------------------------------------------------------
# ETag helpers
# ---------------------------------------------------------------------------


class TestEtagHelpers:
    def test_etag_from_row_version(self):
        assert etag_from_row_version(7) == '"7"'
        assert etag_from_row_version(1) == '"1"'

    def test_parse_if_match_valid(self):
        assert parse_if_match('"7"') == 7
        assert parse_if_match('"123"') == 123

    def test_parse_if_match_none(self):
        assert parse_if_match(None) is None

    def test_parse_if_match_invalid(self):
        assert parse_if_match('"abc"') is None

    def test_parse_if_match_unquoted(self):
        assert parse_if_match("7") == 7
