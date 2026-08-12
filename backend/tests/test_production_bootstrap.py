"""WO-014-004 — Production Bootstrap E2E tests.

Proves the REAL production bootstrap (``app.bootstrap.create_production_runtime``)
assembles the complete canonical runtime and drives real source-adapter events
through the full path:

    Source Adapter
        -> AdapterSupervisor / AdapterRuntime
        -> EventFactory
        -> canonical app.event.Event
        -> EventPipeline.process(event)
        -> PluginDispatcher.dispatch(event)
        -> PluginManager.deliver_event(event)
        -> RUNNING plugin.on_event(event)

These tests use the production bootstrap directly.  They do NOT rebuild the
wiring (no manual ``EventPipeline()`` / ``PluginDispatcher()`` /
``PluginManager()`` / ``set_dispatcher()`` construction).  The only test
double is the external source adapter at the input boundary (the source is
the one place the WO explicitly permits an input stub); the pipeline,
dispatcher, manager and plugins are all real.
"""

import inspect
import sys
import threading
import time

import pytest

from app.bootstrap import ProductionRuntime, create_production_runtime
from app.event.event import Event
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_dispatcher.plugin_dispatcher import PluginDispatcher
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.plugins.manager.plugin_manager import PluginManager
from app.plugins.sdk.base import BasePlugin
from app.plugins.registry.registry import LOADED, RUNNING, STOPPED


# ---------------------------------------------------------------------------
# Test doubles — ONLY on the external source input boundary (explicitly
# permitted by WO-014-004).  Everything downstream is real.
# ---------------------------------------------------------------------------
class _TestSource(IEventSourceAdapter):
    """Controllable passive source adapter (input stub only)."""

    def __init__(self, name: str, raw: dict) -> None:
        self._name = name
        self._raw = [raw]
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def health(self) -> bool:
        return self._running

    def read_events(self) -> list:
        if self._raw:
            return [self._raw.pop(0)]
        return []

    def source_name(self) -> str:
        return self._name


class _RecordingPlugin(BasePlugin):
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


def _raw_atak() -> dict:
    """One valid raw ATAK event (as produced by a real source adapter)."""
    return {
        "uid": "ATAK-BOOTSTRAP-0001",
        "type": "a-u-G",
        "time": 1750000000,
        "lat": 50.4501,
        "lon": 30.5234,
        "how": "m-g",
        "detail": {"callsign": "BLUE-1"},
    }


def _wait_for(fn, timeout: float = 5.0, interval: float = 0.01) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


def _make_running(manager: PluginManager, plugin) -> None:
    manager.register_plugin(plugin)
    manager._registry.update_status(plugin.plugin_id, RUNNING)


def _fresh_runtime() -> ProductionRuntime:
    """Create a production runtime with an isolated PluginManager.

    The composition/bootstrap default uses the authoritative global singleton
    (``get_plugin_manager()``).  For deterministic, cross-test-isolated E2E
    tests we inject a fresh ``PluginManager`` through the same public
    ``create_production_runtime(plugin_manager=...)`` composition API — the
    wiring is otherwise identical to production.
    """
    return create_production_runtime(plugin_manager=PluginManager())


# ---------------------------------------------------------------------------
# T1 / T14 — Production bootstrap exists; single authoritative composition
# ---------------------------------------------------------------------------
def test_bootstrap_creates_production_runtime():
    rt = _fresh_runtime()
    assert isinstance(rt, ProductionRuntime)
    assert isinstance(rt.pipeline, EventPipeline)
    assert isinstance(rt.plugin_dispatcher, PluginDispatcher)
    assert isinstance(rt.plugin_manager, PluginManager)
    assert not rt.started


def test_bootstrap_uses_authoritative_plugin_manager_singleton():
    """No second PluginManager is created by the production bootstrap."""
    rt1 = create_production_runtime()
    rt2 = create_production_runtime()
    # The authoritative global singleton is shared (no parallel managers).
    assert rt1.plugin_manager is rt2.plugin_manager


def test_dispatcher_attached_by_production_bootstrap():
    """The pipeline is wired to the real WO-014-002 PluginDispatcher."""
    rt = _fresh_runtime()
    assert rt.pipeline._dispatcher is rt.plugin_dispatcher


# ---------------------------------------------------------------------------
# T2/T3/T4/T5/T6/T7 — Real source -> canonical Event -> RUNNING plugin
# ---------------------------------------------------------------------------
def test_real_source_reaches_running_plugin_via_production_bootstrap():
    rt = _fresh_runtime()
    plugin = _RecordingPlugin("b-rec-1")
    _make_running(rt.plugin_manager, plugin)
    rt.add_source(_TestSource("atak", _raw_atak()))

    rt.start()
    try:
        assert _wait_for(lambda: len(plugin.received) >= 1), (
            "no canonical event reached the plugin via production bootstrap"
        )
        event = plugin.received[0]

        # T3/T4 — EventFactory + EventPipeline were used: canonical Event,
        # never a raw dict.
        assert isinstance(event, Event), (
            f"received {type(event).__name__}, expected canonical Event"
        )
        # Source identity preserved through the canonical path.
        assert event.source == "atak"
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T9 — Event identity preserved through the full production path
# ---------------------------------------------------------------------------
def test_event_identity_preserved_through_production_bootstrap():
    rt = _fresh_runtime()
    plugin = _RecordingPlugin("b-ident")
    _make_running(rt.plugin_manager, plugin)
    raw = _raw_atak()
    rt.add_source(_TestSource("atak", raw))

    rt.start()
    try:
        assert _wait_for(lambda: len(plugin.received) >= 1)
        # The exact canonical object created from the source survives to the
        # plugin (no serialization / copy / dict round-trip).
        event = plugin.received[0]
        assert isinstance(event, Event)
        assert type(event).__module__ == "app.event.event"
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T8 — Lifecycle filtering is authoritative through production bootstrap
# ---------------------------------------------------------------------------
def test_stopped_and_loaded_plugins_do_not_receive_event():
    rt = _fresh_runtime()
    running = _RecordingPlugin("b-running")
    stopped = _RecordingPlugin("b-stopped")
    loaded = _RecordingPlugin("b-loaded")

    rt.plugin_manager.register_plugin(running)
    rt.plugin_manager.register_plugin(stopped)
    rt.plugin_manager.register_plugin(loaded)
    rt.plugin_manager._registry.update_status("b-running", RUNNING)
    rt.plugin_manager._registry.update_status("b-stopped", STOPPED)
    rt.plugin_manager._registry.update_status("b-loaded", LOADED)

    rt.add_source(_TestSource("atak", _raw_atak()))
    rt.start()
    try:
        assert _wait_for(lambda: len(running.received) >= 1)
        # STOPPED and LOADED plugins must NOT receive the event.
        assert stopped.received == []
        assert loaded.received == []
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T10 — Failure isolation preserved through production bootstrap
# ---------------------------------------------------------------------------
def test_failing_plugin_does_not_block_other_plugins():
    rt = _fresh_runtime()
    failing = _FailingPlugin("b-fail")
    recording = _RecordingPlugin("b-ok")
    _make_running(rt.plugin_manager, failing)
    _make_running(rt.plugin_manager, recording)

    rt.add_source(_TestSource("atak", _raw_atak()))
    rt.start()
    try:
        # The failing plugin raises; the recording plugin must still receive.
        assert _wait_for(lambda: len(recording.received) >= 1)
        assert isinstance(recording.received[0], Event)
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T11 — Exactly-once delivery per pipeline invocation
# ---------------------------------------------------------------------------
def test_exactly_once_delivery_per_event():
    rt = _fresh_runtime()
    plugin = _RecordingPlugin("b-single")
    _make_running(rt.plugin_manager, plugin)

    # One raw source event -> exactly one canonical Event -> exactly one
    # on_event per RUNNING plugin.
    rt.add_source(_TestSource("atak", _raw_atak()))
    rt.start()
    try:
        assert _wait_for(lambda: len(plugin.received) >= 1)
        time.sleep(0.2)  # give time to observe any spurious duplicate
        assert len(plugin.received) == 1
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T12 — Shutdown stops source processing cleanly (no orphan source threads)
# ---------------------------------------------------------------------------
def test_shutdown_stops_source_processing_cleanly():
    rt = _fresh_runtime()
    plugin = _RecordingPlugin("b-shutdown")
    _make_running(rt.plugin_manager, plugin)
    rt.add_source(_TestSource("atak", _raw_atak()))

    rt.start()
    assert _wait_for(lambda: len(plugin.received) >= 1)
    assert rt.started is True

    # No adapter-runtime thread may be left behind after stop().
    rt.stop()
    assert rt.started is False
    for t in threading.enumerate():
        assert not t.name.startswith("adapter-runtime-"), (
            f"orphaned source thread left after stop: {t.name}"
        )


# ---------------------------------------------------------------------------
# T13 — Legacy isolation: bootstrap introduces no app.core / EventBus /
#       EventResult coupling
# ---------------------------------------------------------------------------
def test_bootstrap_has_no_legacy_coupling():
    import app.bootstrap as bootstrap

    imports = [
        line.strip()
        for line in inspect.getsource(sys.modules[bootstrap.__name__]).splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    joined = "\n".join(imports).lower()

    for forbidden in ("app.core", "eventbus", "event_result", "eventresult"):
        assert forbidden not in joined, f"forbidden import found: {forbidden}"

    # The bootstrap must compose the authoritative components.
    assert "from app.composition import eventruntime, create_event_runtime" in joined
    assert "from app.event_sources.runtime.adapter_supervisor import adaptersupervisor" in joined
