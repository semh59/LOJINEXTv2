import enum


class OutboxPublishStatus(str, enum.Enum):
    PENDING = "PENDING"
    READY = "READY"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"
