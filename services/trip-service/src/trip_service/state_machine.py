"""Trip-specific state machine enforcement."""

from __future__ import annotations

from platform_common.state_machine import StateMachine

from trip_service.enums import TripStatus


class TripStateMachine(StateMachine[TripStatus]):  # type: ignore[misc]
    """
    Enforces valid transitions for Trip aggregates.

    Full Lifecycle:
        PLANNED -> ASSIGNED -> IN_PROGRESS -> COMPLETED
        PLANNED -> PENDING_REVIEW -> COMPLETED / REJECTED
        Any non-terminal -> CANCELLED / SOFT_DELETED
        CANCELLED -> SOFT_DELETED (cleanup)
        COMPLETED -> SOFT_DELETED (hard-delete path)
        REJECTED -> SOFT_DELETED (cleanup)
    """

    def __init__(self, current_state: TripStatus):
        super().__init__(
            current_state=current_state,
            valid_transitions={
                TripStatus.PLANNED: {
                    TripStatus.ASSIGNED,
                    TripStatus.PENDING_REVIEW,
                    TripStatus.CANCELLED,
                    TripStatus.SOFT_DELETED,
                },
                TripStatus.ASSIGNED: {
                    TripStatus.IN_PROGRESS,
                    TripStatus.PENDING_REVIEW,
                    TripStatus.CANCELLED,
                    TripStatus.SOFT_DELETED,
                },
                TripStatus.IN_PROGRESS: {
                    TripStatus.COMPLETED,
                    TripStatus.CANCELLED,
                    TripStatus.SOFT_DELETED,
                },
                TripStatus.PENDING_REVIEW: {
                    TripStatus.COMPLETED,
                    TripStatus.REJECTED,
                    TripStatus.CANCELLED,
                    TripStatus.SOFT_DELETED,
                },
                TripStatus.COMPLETED: {
                    TripStatus.SOFT_DELETED,
                },
                TripStatus.REJECTED: {
                    TripStatus.SOFT_DELETED,
                },
                TripStatus.CANCELLED: {
                    TripStatus.SOFT_DELETED,
                },
                TripStatus.SOFT_DELETED: set(),
            },
        )
