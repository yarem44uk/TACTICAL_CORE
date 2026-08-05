"""
Plugin Lifecycle Management.

State machine for plugin lifecycle transitions.
Uses PluginState from base.py as the single source of truth.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.plugins.sdk.base import PluginState


# LifecycleState is an alias to PluginState per ADR-010-004-001.
# All SDK modules import PluginState from base.py — no duplication.
LifecycleState = PluginState


@dataclass
class LifecycleTransition:
    """Record of a lifecycle state transition."""

    from_state: PluginState
    to_state: PluginState
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    success: bool = True
    error: Optional[str] = None


# Valid state transitions (state -> set of allowed next states)
_VALID_TRANSITIONS: Dict[PluginState, set[PluginState]] = {
    PluginState.DISCOVERED: {PluginState.VALIDATED, PluginState.FAILED},
    PluginState.VALIDATED: {PluginState.LOADED, PluginState.FAILED},
    PluginState.LOADED: {PluginState.INITIALIZED, PluginState.FAILED},
    PluginState.INITIALIZED: {PluginState.RUNNING, PluginState.STOPPED, PluginState.FAILED},
    PluginState.RUNNING: {PluginState.STOPPED, PluginState.FAILED, PluginState.INITIALIZED},
    PluginState.STOPPED: {PluginState.INITIALIZED, PluginState.DISABLED, PluginState.UNINSTALLED},
    PluginState.DISABLED: {PluginState.VALIDATED, PluginState.UNINSTALLED},
    PluginState.FAILED: {PluginState.VALIDATED, PluginState.STOPPED, PluginState.DISABLED},
    PluginState.UNINSTALLED: set(),  # terminal
}


class PluginLifecycle:
    """
    State machine for plugin lifecycle management.

    Enforces valid transitions between PluginState values.
    Records transition history for auditing and diagnostics.
    """

    def __init__(self, plugin_id: str) -> None:
        """
        Initialize lifecycle manager.

        Args:
            plugin_id: Unique plugin identifier.
        """
        self._plugin_id = plugin_id
        self._state = PluginState.DISCOVERED
        self._history: List[LifecycleTransition] = []
        self._created_at = datetime.now(timezone.utc)

    @property
    def plugin_id(self) -> str:
        """Plugin identifier."""
        return self._plugin_id

    @property
    def current_state(self) -> PluginState:
        """Current lifecycle state."""
        return self._state

    @property
    def history(self) -> List[LifecycleTransition]:
        """Immutable transition history."""
        return list(self._history)

    @property
    def created_at(self) -> datetime:
        """Lifecycle creation timestamp."""
        return self._created_at

    def can_transition(self, target: PluginState) -> bool:
        """
        Check if a transition to the target state is valid.

        Args:
            target: Target PluginState.

        Returns:
            True if the transition is allowed by the state machine.
        """
        allowed = _VALID_TRANSITIONS.get(self._state, set())
        return target in allowed

    def transition(self, target: PluginState) -> bool:
        """
        Attempt a state transition.

        Args:
            target: Target PluginState.

        Returns:
            True if transition succeeded, False if invalid.
        """
        if not self.can_transition(target):
            self._history.append(LifecycleTransition(
                from_state=self._state,
                to_state=target,
                success=False,
                error=f"Invalid transition: {self._state.value} -> {target.value}",
            ))
            return False

        self._history.append(LifecycleTransition(
            from_state=self._state,
            to_state=target,
            success=True,
        ))
        self._state = target
        return True

    def to_state(self, state: str) -> bool:
        """
        Transition by state name string.

        Args:
            state: State name string (e.g. 'running').

        Returns:
            True if transition succeeded.
        """
        try:
            target = PluginState(state)
        except ValueError:
            self._history.append(LifecycleTransition(
                from_state=self._state,
                to_state=PluginState.DISCOVERED,  # placeholder for invalid
                success=False,
                error=f"Unknown state: {state}",
            ))
            return False
        return self.transition(target)

    def start_sequence(self) -> bool:
        """
        Execute the full start sequence from current state.

        DISCOVERED -> VALIDATED -> LOADED -> INITIALIZED -> RUNNING

        Returns:
            True if the full sequence completed successfully.
        """
        states = [
            PluginState.VALIDATED,
            PluginState.LOADED,
            PluginState.INITIALIZED,
            PluginState.RUNNING,
        ]
        for target in states:
            if not self.transition(target):
                return False
        return True

    def stop_sequence(self) -> bool:
        """
        Execute the stop sequence.

        RUNNING -> STOPPED

        Returns:
            True if the stop sequence completed successfully.
        """
        return self.transition(PluginState.STOPPED)

    def is_terminal(self) -> bool:
        """Check if the plugin is in a terminal state."""
        return self._state in (PluginState.UNINSTALLED,)

    def to_dict(self) -> Dict[str, Any]:
        """Convert lifecycle state to dictionary."""
        return {
            "plugin_id": self._plugin_id,
            "current_state": self._state.value,
            "history": [
                {
                    "from": t.from_state.value,
                    "to": t.to_state.value,
                    "timestamp": t.timestamp.isoformat(),
                    "success": t.success,
                    "error": t.error,
                }
                for t in self._history
            ],
            "created_at": self._created_at.isoformat(),
            "is_terminal": self.is_terminal(),
        }
