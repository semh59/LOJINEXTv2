import enum


class TripStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_REVIEW = "PENDING_REVIEW"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    SOFT_DELETED = "SOFT_DELETED"


class EnrichmentStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    READY = "READY"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class RouteStatus(str, enum.Enum):
    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class SourceType(str, enum.Enum):
    TELEGRAM_TRIP_SLIP = "TELEGRAM_TRIP_SLIP"
    ADMIN_MANUAL = "ADMIN_MANUAL"
    EMPTY_RETURN_ADMIN = "EMPTY_RETURN_ADMIN"
    EXCEL_IMPORT = "EXCEL_IMPORT"


class DataQualityFlag(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvidenceSource(str, enum.Enum):
    TELEGRAM_TRIP_SLIP = "TELEGRAM_TRIP_SLIP"
    ADMIN_MANUAL = "ADMIN_MANUAL"
    EXCEL_IMPORT = "EXCEL_IMPORT"


class EvidenceKind(str, enum.Enum):
    SLIP_IMAGE = "SLIP_IMAGE"
    MANUAL_ENTRY = "MANUAL_ENTRY"
    IMPORT_ROW = "IMPORT_ROW"


class ReviewReasonCode(str, enum.Enum):
    SOURCE_IMPORT = "SOURCE_IMPORT"
    FUTURE_MANUAL = "FUTURE_MANUAL"
    FALLBACK_MINIMAL = "FALLBACK_MINIMAL"
    EXCEL_IMPORT = "EXCEL_IMPORT"
