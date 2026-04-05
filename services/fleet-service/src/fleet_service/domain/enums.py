"""Fleet Service shared enums (Section 8.1 value sets)."""

from enum import StrEnum


class ActorType(StrEnum):
    """Actor types for audit fields."""

    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    SUPER_ADMIN = "SUPER_ADMIN"
    SERVICE = "SERVICE"
    SYSTEM = "SYSTEM"


class OwnershipType(StrEnum):
    """Vehicle/trailer ownership classification."""

    OWNED = "OWNED"
    LEASED = "LEASED"
    THIRD_PARTY = "THIRD_PARTY"


class MasterStatus(StrEnum):
    """Master record status."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class FuelType(StrEnum):
    """Vehicle fuel type."""

    DIESEL = "DIESEL"
    LNG = "LNG"
    CNG = "CNG"
    ELECTRIC = "ELECTRIC"
    HYBRID = "HYBRID"
    OTHER = "OTHER"


class PowertrainType(StrEnum):
    """Vehicle powertrain type."""

    ICE = "ICE"
    BEV = "BEV"
    PHEV = "PHEV"
    HEV = "HEV"
    FCEV = "FCEV"
    OTHER = "OTHER"


class EmissionClass(StrEnum):
    """Vehicle emission class."""

    EURO_3 = "EURO_3"
    EURO_4 = "EURO_4"
    EURO_5 = "EURO_5"
    EURO_6 = "EURO_6"
    OTHER = "OTHER"


class TransmissionType(StrEnum):
    """Vehicle transmission type."""

    MANUAL = "MANUAL"
    AUTOMATED_MANUAL = "AUTOMATED_MANUAL"
    AUTOMATIC = "AUTOMATIC"
    OTHER = "OTHER"


class AxleConfig(StrEnum):
    """Vehicle axle configuration."""

    X4_2 = "4X2"
    X6_2 = "6X2"
    X6_4 = "6X4"
    X8_2 = "8X2"
    X8_4 = "8X4"
    OTHER = "OTHER"


class RoofHeightClass(StrEnum):
    """Vehicle roof height classification."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    OTHER = "OTHER"


class CabType(StrEnum):
    """Vehicle cab type."""

    DAY = "DAY"
    SLEEPER = "SLEEPER"
    OTHER = "OTHER"


class AeroPackageLevel(StrEnum):
    """Aero package level (ordered: NONE < LOW < MEDIUM < HIGH)."""

    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @classmethod
    def ordering(cls) -> dict["AeroPackageLevel", int]:
        """Return ordering map for composite max computation."""
        return {cls.NONE: 0, cls.LOW: 1, cls.MEDIUM: 2, cls.HIGH: 3}


class TireRrClass(StrEnum):
    """Tire rolling resistance class."""

    UNKNOWN = "UNKNOWN"
    STANDARD = "STANDARD"
    LOW_RR = "LOW_RR"
    ULTRA_LOW_RR = "ULTRA_LOW_RR"


class TireType(StrEnum):
    """Tire type."""

    STANDARD = "STANDARD"
    WIDE_BASE = "WIDE_BASE"
    OTHER = "OTHER"


class IdleReductionType(StrEnum):
    """Idle reduction technology type."""

    NONE = "NONE"
    APU = "APU"
    BATTERY_AC = "BATTERY_AC"
    AUTO_START_STOP = "AUTO_START_STOP"
    OTHER = "OTHER"


class TrailerType(StrEnum):
    """Trailer body type classification."""

    DRY_VAN = "DRY_VAN"
    REEFER = "REEFER"
    TANKER = "TANKER"
    FLATBED = "FLATBED"
    CURTAIN = "CURTAIN"
    TIPPER = "TIPPER"
    CONTAINER_CHASSIS = "CONTAINER_CHASSIS"
    OTHER = "OTHER"


class BodyType(StrEnum):
    """Trailer body type."""

    BOX = "BOX"
    TANK = "TANK"
    OPEN = "OPEN"
    CURTAIN = "CURTAIN"
    OTHER = "OTHER"


class ReeferUnitType(StrEnum):
    """Reefer unit type."""

    DIESEL = "DIESEL"
    ELECTRIC = "ELECTRIC"
    HYBRID = "HYBRID"
    OTHER = "OTHER"


class ReeferPowerSource(StrEnum):
    """Reefer power source."""

    SELF_POWERED = "SELF_POWERED"
    TRACTOR_POWERED = "TRACTOR_POWERED"
    GRID_CHARGED = "GRID_CHARGED"
    OTHER = "OTHER"


class PublishStatus(StrEnum):
    """Outbox publish status (no PUBLISHING intermediate state)."""

    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


class DeleteResult(StrEnum):
    """Delete audit result — 7 canonical paths."""

    REJECTED_UNAUTHORIZED = "REJECTED_UNAUTHORIZED"
    REJECTED_NOT_FOUND = "REJECTED_NOT_FOUND"
    REJECTED_ETAG_MISMATCH = "REJECTED_ETAG_MISMATCH"
    REJECTED_NOT_SOFT_DELETED = "REJECTED_NOT_SOFT_DELETED"
    REJECTED_DEPENDENCY_UNAVAILABLE = "REJECTED_DEPENDENCY_UNAVAILABLE"
    REJECTED_REFERENCED = "REJECTED_REFERENCED"
    SUCCEEDED = "SUCCEEDED"


class ReferenceCheckStatus(StrEnum):
    """Delete audit reference check status."""

    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    SUCCEEDED = "SUCCEEDED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"


class AggregateType(StrEnum):
    """Aggregate type for outbox, timeline, delete audit."""

    VEHICLE = "VEHICLE"
    TRAILER = "TRAILER"


class LifecycleState(StrEnum):
    """Derived lifecycle state (computed, not stored)."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SOFT_DELETED = "SOFT_DELETED"
