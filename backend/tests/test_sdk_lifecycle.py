"""
Plugin SDK - Lifecycle Tests.

Tests for PluginLifecycle state machine.
"""

import pytest
import sys
sys.path.insert(0, "/opt/data/tactical_core_github/backend")

from app.plugins.sdk.base import PluginState
from app.plugins.sdk.lifecycle import PluginLifecycle, LifecycleState


class TestPluginLifecycle:
    """PluginLifecycle unit tests."""

    def _make(self) -> PluginLifecycle:
        return PluginLifecycle(plugin_id="test-lifecycle")

    def test_initial_state_is_discovered(self) -> None:
        lc = self._make()
        assert lc.current_state == PluginState.DISCOVERED

    def test_plugin_id_is_stored(self) -> None:
        lc = PluginLifecycle(plugin_id="my-plugin")
        assert lc.plugin_id == "my-plugin"

    def test_can_transition_discovered_to_validated(self) -> None:
        lc = self._make()
        assert lc.can_transition(PluginState.VALIDATED) is True

    def test_transition_discovered_to_validated(self) -> None:
        lc = self._make()
        assert lc.transition(PluginState.VALIDATED) is True
        assert lc.current_state == PluginState.VALIDATED

    def test_transition_discovered_to_failed(self) -> None:
        lc = self._make()
        assert lc.transition(PluginState.FAILED) is True
        assert lc.current_state == PluginState.FAILED

    def test_cannot_transition_discovered_to_running(self) -> None:
        lc = self._make()
        assert lc.can_transition(PluginState.RUNNING) is False
        assert lc.transition(PluginState.RUNNING) is False

    def test_start_sequence(self) -> None:
        lc = self._make()
        assert lc.start_sequence() is True
        assert lc.current_state == PluginState.RUNNING

    def test_stop_sequence_from_running(self) -> None:
        lc = self._make()
        lc.start_sequence()
        assert lc.stop_sequence() is True
        assert lc.current_state == PluginState.STOPPED

    def test_history_records_transitions(self) -> None:
        lc = self._make()
        lc.transition(PluginState.VALIDATED)
        lc.transition(PluginState.LOADED)
        assert len(lc.history) == 2
        assert lc.history[0].success is True
        assert lc.history[1].success is True

    def test_history_records_failed_transition(self) -> None:
        lc = self._make()
        lc.transition(PluginState.RUNNING)
        assert len(lc.history) == 1
        assert lc.history[0].success is False

    def test_terminal_state_uninstalled(self) -> None:
        lc = self._make()
        assert lc.is_terminal() is False
        lc.transition(PluginState.VALIDATED)
        lc.transition(PluginState.LOADED)
        lc.transition(PluginState.INITIALIZED)
        lc.transition(PluginState.STOPPED)
        lc.transition(PluginState.UNINSTALLED)
        assert lc.is_terminal() is True

    def test_to_state_by_string(self) -> None:
        lc = self._make()
        assert lc.to_state("validated") is True
        assert lc.current_state == PluginState.VALIDATED

    def test_to_state_invalid_string(self) -> None:
        lc = self._make()
        assert lc.to_state("nonexistent") is False

    def test_lifecyclestate_alias(self) -> None:
        assert LifecycleState is PluginState
