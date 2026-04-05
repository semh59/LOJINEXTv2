"""Trip-specific state machine enforcement."""

from __future__ import annotations

from platform_common.state_machine import StateMachine

from trip_service.enums import TripStatus


class TripStateMachine(StateMachine[TripStatus]):
    """
    Enforces valid transitions for Trip aggregates.

    Valid Transitions:
    - REQUESTED -> CANCELLED
    - REQUESTED -> REJECTED
    - REQUESTED -> ASSIGNED
    - ASSIGNED -> CANCELLED
    - ASSIGNED -> IN_PROGRESS
    - IN_PROGRESS -> COMPLETED
    - IN_PROGRESS -> CANCELLED (Emergency cases)
    """

    def __init__(self, current_state: TripStatus):
        super().__init__(
            current_state=current_state,
            valid_transitions={
                TripStatus.REQUESTED: {
                    TripStatus.CANCELLED,
                    TripStatus.REJECTED,
                    TripStatus.ASSIGNED,
                },
                TripStatus.ASSIGNED: {
                    TripStatus.CANCELLED,
                    TripStatus.IN_PROGRESS,
                },
                TripStatus.IN_PROGRESS: {
                    TripStatus.COMPLETED,
                    TripStatus.CANCELLED,
                },
                TripStatus.COMPLETED: set(),
                TripStatus.CANCELLED: set(),
                TripStatus.REJECTED: set(),
            },
        )
