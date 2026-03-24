"""Domain enums for Location Service.

Implements all status enums, classification enums, and type enums
referenced across Sections 4–8 of the v0.7 spec.
"""

from enum import StrEnum

# ---------------------------------------------------------------------------
# Section 4.2 — Route pair lifecycle
# ---------------------------------------------------------------------------


class PairStatus(StrEnum):
    """Route pair lifecycle status."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SOFT_DELETED = "SOFT_DELETED"


# ---------------------------------------------------------------------------
# Section 4.3 — Directional identity
# ---------------------------------------------------------------------------


class DirectionCode(StrEnum):
    """Route direction within a pair."""

    FORWARD = "FORWARD"
    REVERSE = "REVERSE"


# ---------------------------------------------------------------------------
# Section 4.5 — Route version lifecycle
# ---------------------------------------------------------------------------


class ProcessingStatus(StrEnum):
    """Route version processing status."""

    CALCULATED_DRAFT = "CALCULATED_DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    DISCARDED = "DISCARDED"


class ValidationResult(StrEnum):
    """Route version validation outcome."""

    PASS_ = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    UNVALIDATED = "UNVALIDATED"


# ---------------------------------------------------------------------------
# Section 4.7 — Processing runs
# ---------------------------------------------------------------------------


class RunStatus(StrEnum):
    """Processing run status."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TriggerType(StrEnum):
    """Processing run trigger type."""

    INITIAL_CALCULATE = "INITIAL_CALCULATE"
    MANUAL_REFRESH = "MANUAL_REFRESH"
    SCHEDULED_REFRESH = "SCHEDULED_REFRESH"
    IMPORT_CALCULATE = "IMPORT_CALCULATE"
    BULK_REFRESH_ITEM = "BULK_REFRESH_ITEM"


class ProviderCallStatus(StrEnum):
    """Per-provider call status within a run."""

    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    UNAVAILABLE = "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Section 4.9 — Bulk refresh jobs
# ---------------------------------------------------------------------------


class BulkRefreshStatus(StrEnum):
    """Bulk refresh job status."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BulkRefreshTriggerType(StrEnum):
    """Bulk refresh trigger type."""

    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"


class BulkRefreshItemStatus(StrEnum):
    """Bulk refresh job item status."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Section 4.11 — Import jobs
# ---------------------------------------------------------------------------


class ImportMode(StrEnum):
    """Import job mode."""

    IMPORT_ONLY = "IMPORT_ONLY"
    IMPORT_AND_CALCULATE = "IMPORT_AND_CALCULATE"


class ImportJobStatus(StrEnum):
    """Import job status."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"


class ImportRowStatus(StrEnum):
    """Import job row status."""

    VALIDATED = "VALIDATED"
    IMPORTED = "IMPORTED"
    CALCULATE_QUEUED = "CALCULATE_QUEUED"
    CALCULATE_SUCCEEDED = "CALCULATE_SUCCEEDED"
    CALCULATE_FAILED = "CALCULATE_FAILED"
    FAILED = "FAILED"
    WARNING_ONLY = "WARNING_ONLY"


class ImportErrorSeverity(StrEnum):
    """Import row error severity."""

    ERROR = "ERROR"
    WARNING = "WARNING"


# ---------------------------------------------------------------------------
# Section 4.14 — Export jobs
# ---------------------------------------------------------------------------


class ExportStatus(StrEnum):
    """Export job status."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ExportVersionScope(StrEnum):
    """Export version scope."""

    ACTIVE_ONLY = "ACTIVE_ONLY"
    ALL_VERSIONS = "ALL_VERSIONS"


# ---------------------------------------------------------------------------
# Section 5.4 — Grade classification
# ---------------------------------------------------------------------------


class GradeClass(StrEnum):
    """Segment grade classification."""

    DOWNHILL_STEEP = "DOWNHILL_STEEP"
    DOWNHILL_MODERATE = "DOWNHILL_MODERATE"
    FLAT = "FLAT"
    UPHILL_MODERATE = "UPHILL_MODERATE"
    UPHILL_STEEP = "UPHILL_STEEP"


# ---------------------------------------------------------------------------
# Section 5.6 — Road classification
# ---------------------------------------------------------------------------


class RoadClass(StrEnum):
    """Segment road classification derived from Mapbox intersections."""

    MOTORWAY = "MOTORWAY"
    MOTORWAY_LINK = "MOTORWAY_LINK"
    TRUNK = "TRUNK"
    TRUNK_LINK = "TRUNK_LINK"
    PRIMARY = "PRIMARY"
    PRIMARY_LINK = "PRIMARY_LINK"
    SECONDARY = "SECONDARY"
    SECONDARY_LINK = "SECONDARY_LINK"
    TERTIARY = "TERTIARY"
    TERTIARY_LINK = "TERTIARY_LINK"
    STREET = "STREET"
    SERVICE = "SERVICE"
    FERRY = "FERRY"
    OTHER = "OTHER"


# ---------------------------------------------------------------------------
# Section 5.6 — Urban classification
# ---------------------------------------------------------------------------


class UrbanClass(StrEnum):
    """Segment urban classification."""

    URBAN = "URBAN"
    NON_URBAN = "NON_URBAN"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Section 5.5 — Speed band
# ---------------------------------------------------------------------------


class SpeedBand(StrEnum):
    """Segment speed band classification."""

    BAND_0_49 = "0_49"
    BAND_50_79 = "50_79"
    BAND_80_PLUS = "80_PLUS"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Section 5.7 — Speed limit state
# ---------------------------------------------------------------------------


class SpeedLimitState(StrEnum):
    """Segment speed limit data availability."""

    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Section 5.8 — Geometry format
# ---------------------------------------------------------------------------


class GeometryFormat(StrEnum):
    """Supported geometry encoding formats."""

    POLYLINE6 = "POLYLINE6"


# ---------------------------------------------------------------------------
# Section 5.3 — Language hint for resolve
# ---------------------------------------------------------------------------


class LanguageHint(StrEnum):
    """Language hint for name resolution."""

    TR = "tr"
    EN = "en"
    AUTO = "auto"
