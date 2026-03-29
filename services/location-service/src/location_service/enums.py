"""Domain enums for Location Service.

Implements all status enums, classification enums, and type enums
referenced across Sections 4-8 of the v0.7 spec.
"""

from enum import StrEnum


class PairStatus(StrEnum):
    """Route pair lifecycle status."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SOFT_DELETED = "SOFT_DELETED"


class DirectionCode(StrEnum):
    """Route direction within a pair."""

    FORWARD = "FORWARD"
    REVERSE = "REVERSE"


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


class GradeClass(StrEnum):
    """Segment grade classification."""

    DOWNHILL_STEEP = "DOWNHILL_STEEP"
    DOWNHILL_MODERATE = "DOWNHILL_MODERATE"
    FLAT = "FLAT"
    UPHILL_MODERATE = "UPHILL_MODERATE"
    UPHILL_STEEP = "UPHILL_STEEP"


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


class UrbanClass(StrEnum):
    """Segment urban classification."""

    URBAN = "URBAN"
    NON_URBAN = "NON_URBAN"
    UNKNOWN = "UNKNOWN"


class SpeedBand(StrEnum):
    """Segment speed band classification."""

    BAND_0_49 = "0_49"
    BAND_50_79 = "50_79"
    BAND_80_PLUS = "80_PLUS"
    UNKNOWN = "UNKNOWN"


class SpeedLimitState(StrEnum):
    """Segment speed limit data availability."""

    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


class GeometryFormat(StrEnum):
    """Supported geometry encoding formats."""

    POLYLINE6 = "POLYLINE6"


class LanguageHint(StrEnum):
    """Language hint for name resolution."""

    TR = "tr"
    EN = "en"
    AUTO = "auto"
