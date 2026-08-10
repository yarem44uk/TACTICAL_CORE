"""
TACTICAL CORE — Adapter Runtime Lifecycle
WO-013-003

Explicit lifecycle state machine for a single AdapterRuntime.

States (only these are allowed):
    STOPPED
    STARTING
    RUNNING
    DEGRADED
    STOPPING
    FAILED

Transitions:
    STOPPED -> STARTING -> RUNNING
    RUNNING <-> DEGRADED
    RUNNING/DEGRADED -> STOPPING -> STOPPED
    RUNNING/DEGRADED -> FAILED
    FAILED -> STARTING   (manual recovery only)

Forbidden:
    FAILED -> RUNNING     (must pass through STARTING)
    STOPPED -> RUNNING    (must pass through STARTING)

CV3: initial state is explicit STOPPED; there is no UNKNOWN state.
"""

from __future__ import annotations

from enum import Enum


class AdapterState(str, Enum):
    """Lifecycle states of an AdapterRuntime."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    FAILED = "failed"

    def __str__(self) -> str:
        return self.value


# Allowed forward transitions. Keys are source states.
_ALLOWED: dict[AdapterState, set[AdapterState]] = {
    AdapterState.STOPPED: {AdapterState.STARTING},
    AdapterState.STARTING: {AdapterState.RUNNING, AdapterState.FAILED, AdapterState.STOPPED},
    AdapterState.RUNNING: {AdapterState.DEGRADED, AdapterState.STOPPING, AdapterState.FAILED},
    AdapterState.DEGRADED: {AdapterState.RUNNING, AdapterState.STOPPING, AdapterState.FAILED},
    AdapterState.STOPPING: {AdapterState.STOPPED, AdapterState.FAILED},
    AdapterState.FAILED: {AdapterState.STARTING, AdapterState.STOPPED},
}


class LifecycleTransitionError(RuntimeError):
    """Raised when an illegal lifecycle transition is attempted."""


def can_transition(current: AdapterState, target: AdapterState) -> bool:
    """Return True if the transition current -> target is allowed."""
    return target in _ALLOWED.get(current, set())


def transition(current: AdapterState, target: AdapterState) -> AdapterState:
    """Validate and perform a state transition.

    Args:
        current: The current state.
        target: The desired next state.

    Returns:
        The new state (target).

    Raises:
        LifecycleTransitionError: If the transition is not allowed.
    """
    if not can_transition(current, target):
        raise LifecycleTransitionError(
            f"Illegal lifecycle transition: {current} -> {target}"
        )
    return target
