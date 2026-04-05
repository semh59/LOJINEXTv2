import enum

from platform_auth import PlatformActorType, PlatformRole


class TripStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


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


class ActorType(str, enum.Enum):
    """Local alias for platform actor types for backward compatibility and trip-specific actors."""

    SUPER_ADMIN = str(PlatformRole.SUPER_ADMIN.value)
    MANAGER = str(PlatformRole.MANAGER.value)
    OPERATOR = str(PlatformRole.OPERATOR.value)
    SERVICE = str(PlatformRole.SERVICE.value)
    SYSTEM = str(PlatformActorType.SYSTEM.value)
    DRIVER = str(PlatformActorType.DRIVER.value)


class OutboxPublishStatus(str, enum.Enum):
    PENDING = "PENDING"
    READY = "READY"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


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
