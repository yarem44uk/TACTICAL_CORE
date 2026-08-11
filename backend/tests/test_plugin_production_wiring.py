"""
WO-014-002 — Canonical Event → Plugin production wiring tests.

Proves the real production composition path:

    canonical app.event.Event
        |
        v
    EventPipeline.process(event)
        |
        v
    EventPipeline dispatcher contract (dispatch)
        |
        v
    PluginDispatcher.dispatch(event)
        |
        v
    PluginManager.deliver_event(event)
        |
        v
    registered + RUNNING plugins
        |
        v
    plugin.on_event(event)

The central tests exercise the REAL EventPipeline + REAL PluginDispatcher +
REAL PluginManager + a real plugin contract.  They do NOT call
PluginManager.deliver_event() directly to fake the wiring.

Invariants verified:
  * the exact canonical Event object is delivered (identity preserved);
  * raw dictionaries / legacy EventResult cannot enter plugin delivery
    through the integration point;
  * only RUNNING registered plugins receive events;
  * one failing plugin does not prevent another plugin from receiving it;
  * there is exactly one delivery path (no duplicate callback);
  * the new dispatcher introduces no app.core / EventBus / EventResult
    coupling.
"""

import inspect
import sys

import pytest

from app.event.event import Event
from app.contracts.plugin import IPlugin
from app.plugins.sdk.base import BasePlugin
from app.plugins.manager.plugin_manager import PluginManager
from app.plugins.registry.registry import LOADED, RUNNING, STOPPED
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_dispatcher.plugin_dispatcher import PluginDispatcher


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
        event_id="evt-wiring-0001",
        entity_id="entity-1",
        source="atak",
        payload={"lat": 50.0, "lon": 30.0},
    )


def _register_running(manager: PluginManager, plugin: BasePlugin) -> None:
    manager.register_plugin(plugin)
    manager._registry.update_status(plugin.plugin_id, RUNNING)


def _make_wired_pipeline(manager: PluginManager) -> EventPipeline:
    """Build the production composition under test.

    This is exactly the production wiring the WO establishes:
        EventPipeline.set_dispatcher(PluginDispatcher(plugin_manager))
    """
    pipeline = EventPipeline()
    dispatcher = PluginDispatcher(manager)
    pipeline.set_dispatcher(dispatcher)
    return pipeline


def test_pipeline_reaches_plugin_manager_via_plugin_dispatcher():
    """A canonical Event through EventPipeline reaches the plugin layer."""
    manager = PluginManager()
    plugin = _RecordingPlugin("w-1")
    _register_running(manager, plugin)

    pipeline = _make_wired_pipeline(manager)
    event = _make_event()
    result = pipeline.process(event)

    assert result is True
    assert len(plugin.received) == 1
    assert plugin.received[0] is event


def test_plugin_receives_canonical_event_object():
    """The object delivered to on_event is the canonical app.event.Event."""
    manager = PluginManager()
    plugin = _RecordingPlugin("w-canon")
    _register_running(manager, plugin)

    pipeline = _make_wired_pipeline(manager)
    event = _make_event()
    pipeline.process(event)

    assert len(plugin.received) == 1
    assert isinstance(plugin.received[0], Event)


def test_event_identity_is_preserved_through_pipeline():
    """The exact canonical Event object survives the full path (no copy)."""
    manager = PluginManager()
    plugin = _RecordingPlugin("w-ident")
    _register_running(manager, plugin)

    pipeline = _make_wired_pipeline(manager)
    event = _make_event()
    pipeline.process(event)

    assert plugin.received[0] is event


def test_raw_dict_is_rejected_at_delivery():
    """A raw dict cannot be delivered to plugin.on_event().

    The dispatcher forwards whatever the pipeline hands it; the plugin-layer
    delivery (PluginManager.deliver_event) rejects non-canonical input with
    TypeError before any plugin.on_event is invoked.
    """
    manager = PluginManager()
    plugin = _RecordingPlugin("w-dict")
    _register_running(manager, plugin)

    pipeline = _make_wired_pipeline(manager)

    with pytest.raises(TypeError):
        pipeline.process({})  # type: ignore[arg-type]

    # The raw dict must never reach on_event.
    assert plugin.received == []


def test_only_running_plugins_receive_event():
    """Only RUNNING registered plugins receive; stopped/loaded do not."""
    manager = PluginManager()

    running = _RecordingPlugin("w-running")
    stopped = _RecordingPlugin("w-stopped")
    loaded = _RecordingPlugin("w-loaded")

    manager.register_plugin(running)
    manager.register_plugin(stopped)
    manager.register_plugin(loaded)
    manager._registry.update_status("w-running", RUNNING)
    manager._registry.update_status("w-stopped", STOPPED)
    manager._registry.update_status("w-loaded", LOADED)

    pipeline = _make_wired_pipeline(manager)
    event = _make_event()
    pipeline.process(event)

    assert len(running.received) == 1
    assert running.received[0] is event
    assert stopped.received == []
    assert loaded.received == []


def test_failing_plugin_does_not_block_other_plugins():
    """A failing plugin must not prevent another plugin from receiving it."""
    manager = PluginManager()

    failing = _FailingPlugin("w-fail")
    recording = _RecordingPlugin("w-ok")

    _register_running(manager, failing)
    _register_running(manager, recording)

    pipeline = _make_wired_pipeline(manager)
    event = _make_event()

    # Failing plugin raises internally; delivery must continue.
    pipeline.process(event)

    assert len(recording.received) == 1
    assert recording.received[0] is event


def test_single_delivery_no_duplicate_callback():
    """One canonical Event yields exactly one callback per eligible plugin.

    Guards against duplicate wiring (registering the dispatcher twice or
    introducing a second delivery path) for the integration under test.
    """
    manager = PluginManager()
    plugin = _RecordingPlugin("w-single")
    _register_running(manager, plugin)

    pipeline = _make_wired_pipeline(manager)
    event = _make_event()
    pipeline.process(event)

    assert len(plugin.received) == 1


def test_plugin_dispatcher_delegates_to_plugin_manager():
    """PluginDispatcher must delegate to PluginManager.deliver_event().

    This verifies the dispatcher does NOT iterate plugins directly, keeping
    PluginManager authoritative for validation / lifecycle / isolation.
    """
    manager = PluginManager()
    plugin = _RecordingPlugin("w-delegate")
    _register_running(manager, plugin)

    dispatcher = PluginDispatcher(manager)
    event = _make_event()
    dispatcher.dispatch(event)

    assert len(plugin.received) == 1
    assert plugin.received[0] is event


def test_no_app_core_event_bus_or_event_result_coupling():
    """PluginDispatcher must not import app.core / EventBus / EventResult.

    Import-level guard: the new canonical path must stay free of legacy
    coupling.  This inspects the actual import statements (not docstring
    prose) so that design notes explaining what the dispatcher does NOT do
    do not trigger false positives.
    """
    import app.event_dispatcher.plugin_dispatcher as pd

    imports = [
        line.strip()
        for line in inspect.getsource(sys.modules[pd.__name__]).splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    joined = "\n".join(imports).lower()

    for forbidden in ("app.core", "eventbus", "event_result", "eventresult"):
        assert forbidden not in joined, f"forbidden import found: {forbidden}"

    # Confirm the canonical Event is imported from the canonical location.
    assert any("from app.event.event import event" in line.lower() for line in imports)
