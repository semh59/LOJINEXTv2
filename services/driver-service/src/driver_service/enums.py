"""Enum types for Driver Service."""

import enum


class DriverStatus(str, enum.Enum):
    """Production driver lifecycle status."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    IN_REVIEW = "IN_REVIEW"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


class PhoneNormalizationStatus(str, enum.Enum):
    """Result of phone normalization attempt."""

    NORMALIZED = "NORMALIZED"
    RAW_UNKNOWN = "RAW_UNKNOWN"
    INVALID = "INVALID"
    MISSING = "MISSING"


class AuditActionType(str, enum.Enum):
    """Action types recorded in the audit log."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    STATUS_CHANGE = "STATUS_CHANGE"
    SOFT_DELETE = "SOFT_DELETE"
    RESTORE = "RESTORE"
    HARD_DELETE = "HARD_DELETE"
    MERGE = "MERGE"
    IMPORT_CREATE = "IMPORT_CREATE"
    IMPORT_UPDATE = "IMPORT_UPDATE"


class OutboxPublishStatus(str, enum.Enum):
    """Outbox row lifecycle status."""

    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


class ImportJobStatus(str, enum.Enum):
    """Async import job lifecycle status."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    CANCELLED = "CANCELLED"


class ImportRowStatus(str, enum.Enum):
    """Per-row import result status."""

    PENDING = "PENDING"
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class ActorRole(str, enum.Enum):
    """Roles used in auth context."""

    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    INTERNAL_SERVICE = "INTERNAL_SERVICE"
    SERVICE = "SERVICE"
