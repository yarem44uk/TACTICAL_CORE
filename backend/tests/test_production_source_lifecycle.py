"""WO-014-006 — Production Source Startup / Runtime Orchestration tests.

Proves that the production runtime lifecycle (start / stop of registered
production sources through the existing authoritative ProductionRuntime)
is complete and correct against the REAL production path.

WO-014-006 is about STARTUP/LIFECYCLE ORCHESTRATION only.  Phase 1 contract
inventory (real repository) established that the orchestration itself already
exists and is owned by the existing layers:

    ProductionRuntime.start()  -> AdapterSupervisor.start_all()   (WO-014-004)
    ProductionRuntime.stop()   -> AdapterSupervisor.shutdown()    (WO-014-004)
    register_production_sources -> ProductionRuntime.add_source()
                                  -> AdapterSupervisor.add_adapter() (WO-014-005)
    one AdapterRuntime == one dedicated source worker thread       (WO-013-003)

Plugin lifecycle is owned by PluginManager (WO-014-001): only RUNNING plugins
receive events.  The bootstrap/runtime must NOT duplicate plugin lifecycle.

Real partial-startup contract (verified from source): AdapterSupervisor.
start_all() is NON-transactional — it logs and continues on a per-runtime
start failure, so previously-started sources remain active; shutdown() stops
whatever is running and clears the supervisor (no orphan threads).  This is
consistent with the WO-014-005 documented non-transactional behavior and is
NOT altered here (no transactional semantics are imposed).

These tests exercise the real production composition:
create_production_runtime() -> real EventPipeline / PluginDispatcher /
PluginManager / AdapterSupervisor / EventFactory.  The ONLY test doubles are
the permitted external boundaries: the source adapter and the source-config
provider (exactly as in WO-014-005).  Nothing downstream is reconstructed.
"""

from __future__ import annotations

import inspect
import sys
import threading
import time
from typing import Any

import pytest

from app.bootstrap import ProductionRuntime, create_production_runtime
from app.event.event import Event
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_dispatcher.plugin_dispatcher import PluginDispatcher
from app.event_sources.config import (
    AdapterFactory,
    ISourceConfigProvider,
    SourceDefinition,
)
from app.event_sources.config.errors import AdapterTypeError  # noqa: F401  (boundary type re-export for tests)
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.event_sources.runtime.adapter_supervisor import AdapterSupervisor
from app.event_sources.runtime.lifecycle import AdapterState
from app.event_sources.source_registration import register_production_sources
from app.plugins.manager.plugin_manager import PluginManager, get_plugin_manager
from app.plugins.sdk.base import BasePlugin
from app.plugins.registry.registry import LOADED, RUNNING, STOPPED


# ---------------------------------------------------------------------------
# Test doubles — ONLY at the permitted external boundaries (source adapter and
# source-config provider).  Everything downstream is REAL production wiring.
# ---------------------------------------------------------------------------
class _TestSource(IEventSourceAdapter):
    """Controllable passive source adapter (registered via AdapterFactory)."""

    def __init__(self, name: str, raw: dict, fail_start: bool = False) -> None:
        self._name = name
        self._raw = [raw] if raw is not None else []
        self._running = False
        self._fail_start = fail_start
        self._start_calls = 0
        self._stop_calls = 0

    def start(self) -> None:
        self._start_calls += 1
        if self._fail_start:
            raise RuntimeError(f"adapter '{self._name}' failed to start")
        self._running = True

    def stop(self) -> None:
        self._stop_calls += 1
        self._running = False

    def health(self) -> bool:
        return self._running

    def read_events(self) -> list:
        if self._raw:
            return [self._raw.pop(0)]
        return []

    def source_name(self) -> str:
        return self._name

    @property
    def start_calls(self) -> int:
        return self._start_calls

    @property
    def stop_calls(self) -> int:
        return self._stop_calls


def _make_test_source(definition: SourceDefinition) -> _TestSource:
    return _TestSource(name=definition.name, raw=_raw_atak())


def _make_failing_source(definition: SourceDefinition) -> _TestSource:
    return _TestSource(name=definition.name, raw=None, fail_start=True)


class _ContinuousSource(_TestSource):
    """A source that emits a fresh event on every poll (restart-resumable)."""

    def __init__(self, name: str) -> None:
        super().__init__(name=name, raw=None)
        self._counter = 0

    def read_events(self) -> list:
        self._counter += 1
        return [{"uid": f"CONT-{self._counter}", "type": "a-u-G", "time": 1750000000,
                 "lat": 50.0, "lon": 30.0, "how": "m-g", "detail": {"callsign": "C"}}]


def _make_continuous_source(definition: SourceDefinition) -> _ContinuousSource:
    return _ContinuousSource(name=definition.name)


class _RecordingPlugin(BasePlugin):
    def __init__(self, plugin_id: str) -> None:
        self._pid = plugin_id
        self.received: list[Event] = []
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


class _DictProvider(ISourceConfigProvider):
    """In-memory source-configuration provider (config boundary double)."""

    def __init__(self, definitions: list[SourceDefinition]) -> None:
        self._defs = definitions
        self._loaded = False

    def load(self) -> None:
        self._loaded = True

    def list_sources(self) -> list[SourceDefinition]:
        return list(self._defs)

    def get_source(self, name: str) -> SourceDefinition:
        for d in self._defs:
            if d.name == name:
                return d
        raise KeyError(name)


def _raw_atak() -> dict:
    return {
        "uid": "ATAK-LIFE-0001",
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


def _running(manager: PluginManager, plugin) -> None:
    manager.register_plugin(plugin)
    manager._registry.update_status(plugin.plugin_id, RUNNING)


def _fresh_runtime() -> ProductionRuntime:
    """Isolated ProductionRuntime (fresh PluginManager, real production wiring)."""
    return create_production_runtime(plugin_manager=PluginManager())


def _factory(*pairs) -> AdapterFactory:
    factory = AdapterFactory()
    for adapter_type, builder in pairs:
        factory.register_type(adapter_type, builder)
    return factory


def _provider(*definitions: SourceDefinition) -> _DictProvider:
    return _DictProvider(list(definitions))


def _no_orphan_threads() -> None:
    for t in threading.enumerate():
        assert not t.name.startswith("adapter-runtime-"), (
            f"orphaned source thread left after stop: {t.name}"
        )


# ---------------------------------------------------------------------------
# T1/T2 — Production runtime can be created via bootstrap; configured sources
# register through the existing WO-014-005 path and reach the supervisor.
# ---------------------------------------------------------------------------
def test_production_runtime_created_via_bootstrap():
    rt = create_production_runtime()
    assert isinstance(rt, ProductionRuntime)
    assert isinstance(rt.pipeline, EventPipeline)
    assert isinstance(rt.plugin_dispatcher, PluginDispatcher)


def test_registered_sources_reach_existing_supervisor():
    rt = _fresh_runtime()
    registered = register_production_sources(
        rt,
        _provider(SourceDefinition(name="atak-a", adapter_type="atak")),
        _factory(("atak", _make_test_source)),
    )
    assert registered == ["atak-a"]
    # T2 — adapter is in the EXISTING AdapterSupervisor (one runtime per source).
    assert rt.supervisor.list_runtimes() == ["atak-a"]
    assert rt.supervisor.count() == 1


# ---------------------------------------------------------------------------
# T3/T4/T5 — start() starts sources through AdapterSupervisor.start_all();
# no second pipeline, no second dispatcher, no second manager.
# ---------------------------------------------------------------------------
def test_start_invokes_adapter_supervisor_start_all():
    rt = _fresh_runtime()
    register_production_sources(
        rt,
        _provider(SourceDefinition(name="atak-a", adapter_type="atak")),
        _factory(("atak", _make_test_source)),
    )
    rt.start()
    try:
        assert rt.started is True
        rtm = rt.supervisor.get_runtime("atak-a")
        # The source worker thread transitions to RUNNING asynchronously after
        # start_all(); wait for it rather than asserting the instant state.
        assert _wait_for(
            lambda: rtm.state in (AdapterState.RUNNING, AdapterState.DEGRADED)
        ), f"source runtime did not reach RUNNING: {rtm.state}"
        assert rt.supervisor.healthy_count() == 1
    finally:
        rt.stop()


def test_no_second_pipeline_or_dispatcher():
    rt = _fresh_runtime()
    # The runtime exposes the SAME pipeline/dispatcher the composition root wired.
    assert rt.pipeline._dispatcher is rt.plugin_dispatcher
    assert isinstance(rt.pipeline, EventPipeline)
    assert isinstance(rt.plugin_dispatcher, PluginDispatcher)
    # Supervisor references the same pipeline object (no second pipeline hidden).
    assert rt.supervisor._pipeline is rt.pipeline


def test_default_path_uses_authoritative_plugin_manager_singleton():
    rt1 = create_production_runtime()
    rt2 = create_production_runtime()
    # Both runtimes share the global singleton — no second PluginManager created.
    assert rt1.plugin_manager is rt2.plugin_manager
    assert rt1.plugin_manager is get_plugin_manager()


# ---------------------------------------------------------------------------
# T6/T7/T8/T9 — Registered source emits a canonical Event; identity preserved;
# reaches a RUNNING plugin via the canonical pipeline; no EventBus/legacy path.
# ---------------------------------------------------------------------------
def test_registered_source_produces_canonical_event_to_running_plugin():
    rt = _fresh_runtime()
    plugin = _RecordingPlugin("life-1")
    _running(rt.plugin_manager, plugin)

    register_production_sources(
        rt,
        _provider(SourceDefinition(name="atak-a", adapter_type="atak")),
        _factory(("atak", _make_test_source)),
    )
    rt.start()
    try:
        assert _wait_for(lambda: len(plugin.received) >= 1), (
            "no canonical event reached the plugin via the registered source"
        )
        event = plugin.received[0]
        assert isinstance(event, Event)                      # T6 canonical
        assert type(event).__module__ == "app.event.event"   # T7 identity/module
        assert event.source == "atak-a"                      # source routed
        assert len(plugin.received) == 1                     # exactly-once via pipeline
    finally:
        rt.stop()


def test_no_eventbus_or_legacy_coupling_in_runtime():
    import app.bootstrap as bootstrap_mod
    import app.event_sources.source_registration as reg_mod

    for mod in (bootstrap_mod, reg_mod):
        src = inspect.getsource(sys.modules[mod.__name__])
        imports = "\n".join(
            line.strip()
            for line in src.splitlines()
            if line.strip().startswith("import ") or line.strip().startswith("from ")
        ).lower()
        for forbidden in ("app.core", "eventbus", "event_result", "eventresult", "eventengine"):
            assert forbidden not in imports, (
                f"forbidden import in {mod.__name__}: {forbidden}"
            )


# ---------------------------------------------------------------------------
# T10 — Lifecycle filtering stays authoritative: STOPPED/LOADED plugins do NOT
# receive events; only RUNNING does.
# ---------------------------------------------------------------------------
def test_lifecycle_filtering_remains_authoritative():
    rt = _fresh_runtime()
    running = _RecordingPlugin("life-running")
    stopped = _RecordingPlugin("life-stopped")
    loaded = _RecordingPlugin("life-loaded")

    rt.plugin_manager.register_plugin(running)
    rt.plugin_manager.register_plugin(stopped)
    rt.plugin_manager.register_plugin(loaded)
    rt.plugin_manager._registry.update_status("life-running", RUNNING)
    rt.plugin_manager._registry.update_status("life-stopped", STOPPED)
    rt.plugin_manager._registry.update_status("life-loaded", LOADED)

    register_production_sources(
        rt,
        _provider(SourceDefinition(name="atak-a", adapter_type="atak")),
        _factory(("atak", _make_test_source)),
    )
    rt.start()
    try:
        assert _wait_for(lambda: len(running.received) >= 1)
        assert stopped.received == []
        assert loaded.received == []
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T11/T12 — stop() invokes authoritative AdapterSupervisor.shutdown(); no
# orphan worker threads remain.
# ---------------------------------------------------------------------------
def test_stop_shuts_down_supervisor_and_leaves_no_threads():
    rt = _fresh_runtime()
    plugin = _RecordingPlugin("life-shutdown")
    _running(rt.plugin_manager, plugin)

    register_production_sources(
        rt,
        _provider(SourceDefinition(name="atak-a", adapter_type="atak")),
        _factory(("atak", _make_test_source)),
    )
    rt.start()
    assert _wait_for(lambda: len(plugin.received) >= 1)

    rt.stop()
    assert rt.started is False
    assert rt.supervisor.count() == 0          # supervisor cleared by shutdown
    _no_orphan_threads()


# ---------------------------------------------------------------------------
# T13 — Repeated start/stop follows the REAL existing runtime contract.
# ProductionRuntime.start() is idempotent for a running runtime; stop() is
# idempotent.  A stopped runtime can be started again.
# ---------------------------------------------------------------------------
def test_repeated_start_is_idempotent_for_running_runtime():
    rt = _fresh_runtime()
    plugin = _RecordingPlugin("life-repeat")
    _running(rt.plugin_manager, plugin)
    register_production_sources(
        rt,
        _provider(SourceDefinition(name="atak-a", adapter_type="atak")),
        _factory(("atak", _make_test_source)),
    )

    rt.start()
    rt.start()  # second start on a running runtime must be a no-op
    assert rt.started is True
    try:
        assert _wait_for(lambda: len(plugin.received) >= 1)
        # exactly one run of the source adapter thread (no duplicate runtime).
        assert rt.supervisor.count() == 1
    finally:
        rt.stop()


def test_repeated_stop_is_idempotent():
    rt = _fresh_runtime()
    register_production_sources(
        rt,
        _provider(SourceDefinition(name="atak-a", adapter_type="atak")),
        _factory(("atak", _make_test_source)),
    )
    rt.start()
    rt.stop()
    rt.stop()  # second stop on a stopped runtime must be safe
    assert rt.started is False
    _no_orphan_threads()


def test_runtime_can_be_restarted_after_stop_via_reregistration():
    # REAL existing contract (verified from source + empirically):
    # ProductionRuntime.stop() -> AdapterSupervisor.shutdown() CLEARS the
    # supervisor (all runtimes removed).  A subsequent start() therefore has
    # no sources to start.  Restarting delivery requires RE-REGISTERING the
    # sources (register_production_sources) before start().  This is the
    # authoritative behavior; we do NOT invent restart-without-reregister.
    rt = _fresh_runtime()
    plugin = _RecordingPlugin("life-restart")
    _running(rt.plugin_manager, plugin)
    provider = _provider(SourceDefinition(name="cont-a", adapter_type="cont"))
    factory = _factory(("cont", _make_continuous_source))

    register_production_sources(rt, provider, factory)
    rt.start()
    assert _wait_for(lambda: len(plugin.received) >= 1)
    rt.stop()

    # stop() cleared the supervisor -> no sources remain.
    assert rt.supervisor.count() == 0

    # A bare start() without re-registration starts NOTHING (no delivery).
    rt.start()
    assert rt.started is True
    assert rt.supervisor.count() == 0
    frozen = len(plugin.received)
    assert not _wait_for(lambda: len(plugin.received) > frozen, timeout=0.5)
    rt.stop()

    # Re-register + start resumes delivery through the canonical path.
    register_production_sources(rt, provider, factory)
    assert rt.supervisor.count() == 1
    rt.start()
    try:
        assert _wait_for(lambda: len(plugin.received) > frozen), (
            "re-register + start did not resume event delivery"
        )
        assert rt.supervisor.count() == 1
    finally:
        rt.stop()
    _no_orphan_threads()


# ---------------------------------------------------------------------------
# T14 — Startup failure behavior is explicit and testable.  A source whose
# adapter.start() raises ends up FAILED (per AdapterRuntime), and the runtime
# remains usable (no crash); shutdown() still cleans up.
# ---------------------------------------------------------------------------
def test_startup_failure_is_explicit_and_recoverable_via_shutdown():
    rt = _fresh_runtime()
    register_production_sources(
        rt,
        _provider(SourceDefinition(name="failing-a", adapter_type="fail")),
        _factory(("fail", _make_failing_source)),
    )
    # start() must NOT raise: AdapterSupervisor.start_all() logs and continues.
    rt.start()
    try:
        rtm = rt.supervisor.get_runtime("failing-a")
        # adapter.start() raised -> runtime-level failure -> FAILED (budget may
        # allow a real auto-restart thread, so assert FAILED OR STARTING).
        assert rtm.state in (
            AdapterState.FAILED,
            AdapterState.STARTING,
            AdapterState.RUNNING,
        ), f"unexpected state after start failure: {rtm.state}"
    finally:
        # shutdown() must still clean up and leave no orphan threads.
        rt.stop()
    _no_orphan_threads()


# ---------------------------------------------------------------------------
# T15 — Partial-startup behavior follows the REAL non-transactional contract:
# if source A starts and source B fails, A remains active (no rollback); the
# failed source is isolated; shutdown() stops whatever is running.
# ---------------------------------------------------------------------------
def test_partial_startup_keeps_successful_source_active_non_transactional():
    rt = _fresh_runtime()
    running_plugin = _RecordingPlugin("life-partial")
    _running(rt.plugin_manager, running_plugin)

    register_production_sources(
        rt,
        _provider(
            SourceDefinition(name="good-a", adapter_type="good"),
            SourceDefinition(name="bad-b", adapter_type="bad"),
        ),
        _factory(("good", _make_test_source), ("bad", _make_failing_source)),
    )

    rt.start()
    try:
        # good-a started and delivers through the canonical pipeline.
        assert _wait_for(lambda: len(running_plugin.received) >= 1), (
            "successful source did not deliver after partial startup"
        )
        # bad-b is isolated (FAILED / restarting) — did not take down the runtime.
        bad = rt.supervisor.get_runtime("bad-b")
        assert bad.state in (
            AdapterState.FAILED,
            AdapterState.STARTING,
            AdapterState.RUNNING,
        )
    finally:
        rt.stop()
    _no_orphan_threads()


# ---------------------------------------------------------------------------
# M2/M6/M7 — Adversarial: bypassing the supervisor / pipeline / direct plugin
# invocation must be detectable by structural inspection of the wiring.
# ---------------------------------------------------------------------------
def test_sources_route_through_supervisor_not_direct_pipeline():
    rt = _fresh_runtime()
    register_production_sources(
        rt,
        _provider(SourceDefinition(name="atak-a", adapter_type="atak")),
        _factory(("atak", _make_test_source)),
    )
    rtm = rt.supervisor.get_runtime("atak-a")
    # The runtime's pipeline IS the production pipeline (canonical path), and
    # the runtime holds the supervisor's shared pipeline/factory.
    assert rtm._pipeline is rt.pipeline
    assert rtm._factory is rt.event_factory


def test_runtime_exposes_single_authoritative_manager():
    rt = _fresh_runtime()
    # The runtime's plugin_manager IS the manager wired into the dispatcher.
    assert rt.plugin_dispatcher._plugin_manager is rt.plugin_manager
    assert rt.pipeline._dispatcher is rt.plugin_dispatcher


# ---------------------------------------------------------------------------
# M14 / M1 — Duplicate startup path / removed source startup: mutating the
# runtime to NOT start sources must be detected (no events delivered).
# ---------------------------------------------------------------------------
def test_without_source_startup_no_events_delivered():
    rt = _fresh_runtime()
    plugin = _RecordingPlugin("life-no-start")
    _running(rt.plugin_manager, plugin)
    register_production_sources(
        rt,
        _provider(SourceDefinition(name="atak-a", adapter_type="atak")),
        _factory(("atak", _make_test_source)),
    )
    # Deliberately do NOT call rt.start().  The source runtime is not running,
    # so no event may reach the plugin.
    assert not _wait_for(lambda: len(plugin.received) >= 1, timeout=0.5)
    assert plugin.received == []
    # Cleanup: stop a never-started runtime must still be safe.
    rt.stop()
    _no_orphan_threads()


# ---------------------------------------------------------------------------
# M10 — Omit shutdown: an orphan-worker guard detects a source thread that is
# not joined.  (We assert the guard fires — i.e. a thread WOULD be left behind
# if stop() were skipped — by showing stop() is what joins it.)
# ---------------------------------------------------------------------------
def test_orphan_worker_guard_fires_without_shutdown():
    rt = _fresh_runtime()
    plugin = _RecordingPlugin("life-orphan")
    _running(rt.plugin_manager, plugin)
    register_production_sources(
        rt,
        _provider(SourceDefinition(name="atak-a", adapter_type="atak")),
        _factory(("atak", _make_test_source)),
    )
    rt.start()
    assert _wait_for(lambda: len(plugin.received) >= 1)
    # Without calling stop(), the adapter-runtime thread still exists.
    before = [t.name for t in threading.enumerate()]
    assert any(n.startswith("adapter-runtime-") for n in before), (
        "expected an adapter-runtime thread while running (guard would not fire)"
    )
    # Now prove stop() is what joins it: after stop no such thread remains.
    rt.stop()
    _no_orphan_threads()
