"""Trip-specific state machine enforcement."""

from __future__ import annotations

from platform_common.state_machine import StateMachine

from trip_service.enums import TripStatus


class TripStateMachine(StateMachine[TripStatus]):
    """
    Enforces valid transitions for Trip aggregates.

    Valid Transitions:
    - PENDING_REVIEW -> COMPLETED
    - PENDING_REVIEW -> REJECTED
    """

    def __init__(self, current_state: TripStatus):
        super().__init__(
            current_state=current_state,
            valid_transitions={
                TripStatus.PENDING_REVIEW: {
                    TripStatus.COMPLETED,
                    TripStatus.REJECTED,
                },
                TripStatus.COMPLETED: set(),
                TripStatus.REJECTED: set(),
                TripStatus.SOFT_DELETED: set(),
            },
        )
