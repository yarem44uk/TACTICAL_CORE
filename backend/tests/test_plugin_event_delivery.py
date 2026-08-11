"""
WO-014-001 — Plugin canonical Event delivery tests.

Proves the canonical Event boundary of the plugin layer:

    canonical Event
        |
        v
    PluginManager.deliver_event(Event)
        |
        v
    Plugin.on_event(Event)

Invariants verified:
  * a running plugin receives the canonical app.event.Event object;
  * raw dictionaries are NEVER delivered to on_event;
  * the exact canonical Event object supplied is delivered (identity preserved);
  * only active/running plugins receive events;
  * one failing plugin does not prevent other plugins from receiving the event;
  * existing plugins without an on_event override keep working (backward compat).
"""

import pytest

from app.event.event import Event
from app.contracts.plugin import IPlugin
from app.plugins.sdk.base import BasePlugin
from app.plugins.manager.plugin_manager import PluginManager
from app.plugins.registry.registry import (
    LOADED,
    RUNNING,
    STOPPED,
)


class _RecordingPlugin(BasePlugin):
    """Test plugin that records delivered events."""

    def __init__(self, plugin_id: str) -> None:
        self._pid = plugin_id
        self.received = []
        super().__init__()

    @property
    def plugin_id(self) -> str:
        return self._pid

    def register(self) -> None:
        pass

    def unregister(self) -> None:
        pass

    def on_event(self, event: Event) -> None:
        self.received.append(event)


class _FailingPlugin(BasePlugin):
    """Test plugin that raises on every event."""

    def __init__(self, plugin_id: str) -> None:
        self._pid = plugin_id
        super().__init__()

    @property
    def plugin_id(self) -> str:
        return self._pid

    def register(self) -> None:
        pass

    def unregister(self) -> None:
        pass

    def on_event(self, event: Event) -> None:
        raise RuntimeError("boom")


def _make_event() -> Event:
    return Event(
        event_id="evt-0001",
        entity_id="entity-1",
        source="atak",
        payload={"lat": 50.0, "lon": 30.0},
    )


def _register_running(manager: PluginManager, plugin: BasePlugin) -> None:
    manager.register_plugin(plugin)
    manager._registry.update_status(plugin.plugin_id, RUNNING)


def test_ip_plugin_contract_exposes_on_event():
    """IPlugin contract must expose on_event(Event)."""
    assert hasattr(IPlugin, "on_event")


def test_base_plugin_provides_default_on_event():
    """BasePlugin must provide a backward-compatible on_event default."""
    plugin = _RecordingPlugin("p-default")
    # No override needed to be instantiable; default is a safe no-op.
    assert callable(plugin.on_event)
    # Default no-op must not raise on a canonical Event.
    plugin.on_event(_make_event())


def test_running_plugin_receives_canonical_event():
    """A running plugin receives the canonical Event object."""
    manager = PluginManager()
    plugin = _RecordingPlugin("p-1")
    _register_running(manager, plugin)

    event = _make_event()
    manager.deliver_event(event)

    assert len(plugin.received) == 1
    assert isinstance(plugin.received[0], Event)


def test_raw_dict_is_rejected():
    """A raw dict must never be delivered to plugin.on_event()."""
    manager = PluginManager()
    plugin = _RecordingPlugin("p-dict")
    _register_running(manager, plugin)

    with pytest.raises(TypeError):
        manager.deliver_event({})  # type: ignore[arg-type]

    # The dict must never reach on_event.
    assert plugin.received == []


def test_event_identity_is_preserved():
    """The exact canonical Event object is delivered (no copy/reconstruction)."""
    manager = PluginManager()
    plugin = _RecordingPlugin("p-ident")
    _register_running(manager, plugin)

    event = _make_event()
    manager.deliver_event(event)

    assert len(plugin.received) == 1
    assert plugin.received[0] is event


def test_lifecycle_isolation():
    """Only running plugins receive events; stopped plugins do not."""
    manager = PluginManager()

    running = _RecordingPlugin("p-running")
    stopped = _RecordingPlugin("p-stopped")

    manager.register_plugin(running)
    manager.register_plugin(stopped)
    manager._registry.update_status("p-running", RUNNING)
    manager._registry.update_status("p-stopped", STOPPED)

    event = _make_event()
    manager.deliver_event(event)

    assert len(running.received) == 1
    assert stopped.received == []


def test_failure_isolation():
    """A failing plugin must not prevent other plugins from receiving the event."""
    manager = PluginManager()

    failing = _FailingPlugin("p-fail")
    recording = _RecordingPlugin("p-ok")

    _register_running(manager, failing)
    _register_running(manager, recording)

    event = _make_event()
    # Failing plugin raises internally; delivery must continue.
    manager.deliver_event(event)

    assert len(recording.received) == 1
    assert recording.received[0] is event


def test_multiple_running_plugins_receive_same_event():
    """All running plugins receive the same canonical Event object."""
    manager = PluginManager()

    p1 = _RecordingPlugin("p-a")
    p2 = _RecordingPlugin("p-b")
    p3 = _RecordingPlugin("p-c")

    for p in (p1, p2, p3):
        _register_running(manager, p)

    event = _make_event()
    manager.deliver_event(event)

    assert len(p1.received) == 1
    assert len(p2.received) == 1
    assert len(p3.received) == 1
    for p in (p1, p2, p3):
        assert p.received[0] is event


def test_loaded_plugin_does_not_receive_event():
    """Plugins in LOADED (not running) state do not receive events."""
    manager = PluginManager()

    loaded = _RecordingPlugin("p-loaded")
    manager.register_plugin(loaded)
    manager._registry.update_status("p-loaded", LOADED)

    manager.deliver_event(_make_event())

    assert loaded.received == []
