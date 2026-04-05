"""Generic State Machine implementation for LOJINEXT core services."""

from __future__ import annotations

from typing import Generic, TypeVar, Set, Dict

S = TypeVar("S")  # State type (Enum)


class StateMachine(Generic[S]):
    """
    Enforces valid state transitions for an aggregate.
    """

    def __init__(
        self,
        current_state: S,
        valid_transitions: Dict[S, Set[S]],
    ):
        self.current_state = current_state
        self.valid_transitions = valid_transitions

    def can_transition_to(self, next_state: S) -> bool:
        """Check if a transition to next_state is valid."""
        # Allow transition to the same state (idempotency)
        if self.current_state == next_state:
            return True

        allowed = self.valid_transitions.get(self.current_state, set())
        return next_state in allowed

    def transition_to(self, next_state: S) -> S:
        """
        Transition to next_state or raise ValueError if invalid.
        Returns the new state.
        """
        if not self.can_transition_to(next_state):
            raise ValueError(
                f"Invalid state transition: {self.current_state} -> {next_state}"
            )

        self.current_state = next_state
        return self.current_state
