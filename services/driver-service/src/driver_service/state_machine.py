from __future__ import annotations

from platform_common.state_machine import StateMachine

from driver_service.enums import DriverStatus


class DriverStateMachine(StateMachine[DriverStatus]):
    """
    Formal state machine for the Driver lifecycle.
    """

    def __init__(self, current_state: DriverStatus):
        super().__init__(
            current_state=current_state,
            valid_transitions={
                DriverStatus.IN_REVIEW: {DriverStatus.ACTIVE, DriverStatus.CANCELLED},
                DriverStatus.ACTIVE: {
                    DriverStatus.INACTIVE,
                    DriverStatus.SUSPENDED,
                    DriverStatus.CANCELLED,
                },
                DriverStatus.INACTIVE: {DriverStatus.ACTIVE, DriverStatus.CANCELLED},
                DriverStatus.SUSPENDED: {DriverStatus.ACTIVE, DriverStatus.CANCELLED},
                DriverStatus.CANCELLED: set(),  # Terminal state
            },
        )
