"""Enum types for Trip Service.

All enums are defined per V8 Sections 5.1–5.5.
"""

import enum


class TripStatus(str, enum.Enum):
    """V8 Section 5.1 — Business status."""

    PENDING_REVIEW = "PENDING_REVIEW"
    COMPLETED = "COMPLETED"
    SOFT_DELETED = "SOFT_DELETED"


class EnrichmentStatus(str, enum.Enum):
    """V8 Section 5.2 — Enrichment status."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    READY = "READY"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class RouteStatus(str, enum.Enum):
    """V8 Section 5.3 — Route status."""

    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class SourceType(str, enum.Enum):
    """V8 Section 5.5 — Source type."""

    TELEGRAM_TRIP_SLIP = "TELEGRAM_TRIP_SLIP"
    ADMIN_MANUAL = "ADMIN_MANUAL"
    EXCEL_IMPORT = "EXCEL_IMPORT"
    EMPTY_RETURN_ADMIN = "EMPTY_RETURN_ADMIN"


class DataQualityFlag(str, enum.Enum):
    """V8 Section 6.3 — Data quality flag computed at enrichment."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ActorType(str, enum.Enum):
    """V8 Section 4 — Caller identity."""

    ADMIN = "ADMIN"
    DRIVER = "DRIVER"
    SYSTEM = "SYSTEM"


class ImportJobStatus(str, enum.Enum):
    """V8 Section 6.5 — Import job status."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ImportMode(str, enum.Enum):
    """V8 Section 12.6 — Import mode."""

    STRICT = "STRICT"
    PARTIAL = "PARTIAL"


class ImportRowStatus(str, enum.Enum):
    """V8 Section 6.6 — Import job row status."""

    PENDING = "PENDING"
    IMPORTED = "IMPORTED"
    REJECTED = "REJECTED"


class ExportJobStatus(str, enum.Enum):
    """V8 Section 6.7 — Export job status."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class OutboxPublishStatus(str, enum.Enum):
    """V8 Section 6.8 — Outbox publish status."""

    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


class EvidenceSource(str, enum.Enum):
    """V8 Section 6.2 — Evidence source."""

    TELEGRAM_TRIP_SLIP = "TELEGRAM_TRIP_SLIP"
    EXCEL_IMPORT = "EXCEL_IMPORT"
    ADMIN_MANUAL = "ADMIN_MANUAL"


class EvidenceKind(str, enum.Enum):
    """V8 Section 6.2 — Evidence kind."""

    SLIP_IMAGE = "SLIP_IMAGE"
    IMPORT_ROW = "IMPORT_ROW"
    MANUAL_ENTRY = "MANUAL_ENTRY"
