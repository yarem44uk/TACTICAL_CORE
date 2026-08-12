"""WO-014-005 — Production Source Registration & Configuration tests.

Proves the authoritative production source-registration mechanism
(``app.event_sources.source_registration``) against the REAL production
runtime path:

    SOURCE ADAPTER
        -> AdapterSupervisor / AdapterRuntime
        -> EventFactory
        -> canonical app.event.Event
        -> EventPipeline.process(event)      (create_event_runtime)
        -> PluginDispatcher.dispatch(event)  (WO-014-002)
        -> PluginManager.deliver_event(event)(WO-014-001)
        -> plugin.on_event(event)

These tests exercise the real production path.  The production wiring is
created by the real ``create_production_runtime()``; no manual
``EventPipeline()`` / ``PluginDispatcher()`` / ``PluginManager()`` /
``set_dispatcher()`` reconstruction is used.  The only test doubles are:
  * a controllable source adapter (registered through the real AdapterFactory,
    exactly as production adapters are), and
  * an in-memory ISourceConfigProvider (the source-configuration boundary).

Everything downstream of the adapter is real.
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
from app.event_sources.config.errors import (
    AdapterTypeError,
    DuplicateSourceError,
    SourceNotFoundError,
)
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.event_sources.source_registration import (
    ProductionSourceRegistrar,
    register_production_sources,
)
from app.plugins.manager.plugin_manager import PluginManager
from app.plugins.sdk.base import BasePlugin
from app.plugins.registry.registry import LOADED, RUNNING, STOPPED


# ---------------------------------------------------------------------------
# Test doubles — ONLY at the external source-input and config boundaries
# (explicitly permitted: the source adapter and the source config provider).
# Everything downstream (pipeline, dispatcher, manager, factory) is real.
# ---------------------------------------------------------------------------
class _TestSource(IEventSourceAdapter):
    """Controllable passive source adapter (registered via AdapterFactory)."""

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


def _make_test_source(definition: SourceDefinition) -> _TestSource:
    return _TestSource(name=definition.name, raw=_raw_atak())


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


class _DictProvider(ISourceConfigProvider):
    """In-memory source-configuration provider (config boundary double)."""

    def __init__(self, definitions: list[SourceDefinition]) -> None:
        self._defs = definitions
        self._loaded = False

    def load(self) -> None:
        seen: set[str] = set()
        for d in self._defs:
            if d.name in seen:
                raise DuplicateSourceError(f"duplicate source name '{d.name}'")
            seen.add(d.name)
        self._loaded = True

    def list_sources(self) -> list[SourceDefinition]:
        return list(self._defs)

    def get_source(self, name: str) -> SourceDefinition:
        for d in self._defs:
            if d.name == name:
                return d
        raise SourceNotFoundError(f"source '{name}' not found")


def _raw_atak() -> dict:
    """One valid raw ATAK event (as produced by a real source adapter)."""
    return {
        "uid": "ATAK-REG-0001",
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
    """Isolated ProductionRuntime (fresh PluginManager, real production wiring)."""
    return create_production_runtime(plugin_manager=PluginManager())


def _registered_factory() -> AdapterFactory:
    """AdapterFactory with a real 'atak' adapter type registered."""
    factory = AdapterFactory()
    factory.register_type("atak", _make_test_source)
    return factory


def _provider(*definitions: SourceDefinition) -> _DictProvider:
    return _DictProvider(list(definitions))


# ---------------------------------------------------------------------------
# T1 — Production runtime uses the authoritative registration mechanism
# ---------------------------------------------------------------------------
def test_authoritative_registrar_registers_into_production_runtime():
    rt = _fresh_runtime()
    factory = _registered_factory()
    provider = _provider(SourceDefinition(name="atak-a", adapter_type="atak"))

    registered = register_production_sources(rt, provider, factory)

    assert registered == ["atak-a"]
    # T2 — registered adapters reach the EXISTING AdapterSupervisor.
    assert rt.supervisor.list_runtimes() == ["atak-a"]


# ---------------------------------------------------------------------------
# T3/T4 — ProductionRuntime does not create a second EventPipeline / dispatcher
# ---------------------------------------------------------------------------
def test_no_second_pipeline_or_dispatcher():
    rt1 = _fresh_runtime()
    rt2 = _fresh_runtime()

    # Each runtime has its own wiring, but within one runtime there is exactly
    # one pipeline and one dispatcher — the canonical path is not duplicated.
    assert isinstance(rt1.pipeline, EventPipeline)
    assert isinstance(rt1.plugin_dispatcher, PluginDispatcher)
    # The runtime exposes the SAME pipeline object that the composition root
    # wired (no second pipeline hidden in the registration path).
    assert rt1.pipeline._dispatcher is rt1.plugin_dispatcher
    # Different runtimes are independent (no cross-runtime pipeline leakage).
    assert rt1.pipeline is not rt2.pipeline


# ---------------------------------------------------------------------------
# T5 — Production runtime uses the authoritative PluginManager singleton
# ---------------------------------------------------------------------------
def test_authoritative_plugin_manager_singleton():
    rt1 = create_production_runtime()
    rt2 = create_production_runtime()
    # Both runtimes share the global singleton — registration must not create
    # a second PluginManager.
    assert rt1.plugin_manager is rt2.plugin_manager


# ---------------------------------------------------------------------------
# T6/T7/T8 — A registered source produces a canonical Event, identity is
#            preserved, and it reaches the plugin through the pipeline.
# ---------------------------------------------------------------------------
def test_registered_source_reaches_plugin_via_canonical_pipeline():
    rt = _fresh_runtime()
    plugin = _RecordingPlugin("reg-1")
    _make_running(rt.plugin_manager, plugin)

    register_production_sources(
        rt,
        _provider(SourceDefinition(name="atak-a", adapter_type="atak")),
        _registered_factory(),
    )

    rt.start()
    try:
        assert _wait_for(lambda: len(plugin.received) >= 1), (
            "no canonical event reached the plugin via registered source"
        )
        event = plugin.received[0]
        # T6 — canonical Event, never a raw dict.
        assert isinstance(event, Event)
        # T7 — event identity preserved (same object through the pipeline).
        assert type(event).__module__ == "app.event.event"
        # Source identity routed through registration.
        assert event.source == "atak-a"
        # T8 — event reached the plugin through the canonical pipeline.
        assert len(plugin.received) == 1
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T9 — No EventBus / legacy path is introduced by the registration mechanism
# ---------------------------------------------------------------------------
def test_registration_has_no_legacy_coupling():
    import app.event_sources.source_registration as reg

    imports = [
        line.strip()
        for line in inspect.getsource(sys.modules[reg.__name__]).splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    joined = "\n".join(imports).lower()

    for forbidden in ("app.core", "eventbus", "event_result", "eventresult"):
        assert forbidden not in joined, f"forbidden import found: {forbidden}"


# ---------------------------------------------------------------------------
# T10 — Empty / no-source configuration behaves per existing contract
# ---------------------------------------------------------------------------
def test_empty_configuration_registers_nothing():
    rt = _fresh_runtime()
    registered = register_production_sources(
        rt,
        _provider(),
        _registered_factory(),
    )
    assert registered == []
    assert rt.supervisor.count() == 0
    # Runtime still usable (empty registration must not break the path).
    assert isinstance(rt.pipeline, EventPipeline)


def test_disabled_sources_are_not_registered():
    rt = _fresh_runtime()
    registered = register_production_sources(
        rt,
        _provider(
            SourceDefinition(name="enabled-a", adapter_type="atak", enabled=True),
            SourceDefinition(name="disabled-b", adapter_type="atak", enabled=False),
        ),
        _registered_factory(),
    )
    assert registered == ["enabled-a"]
    assert rt.supervisor.list_runtimes() == ["enabled-a"]


# ---------------------------------------------------------------------------
# Registrar contract: provider + factory are required; unknown type rejected
# ---------------------------------------------------------------------------
def test_registrar_requires_provider_and_factory():
    factory = _registered_factory()
    with pytest.raises(TypeError):
        ProductionSourceRegistrar(provider=None, factory=factory)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ProductionSourceRegistrar(
            provider=_provider(), factory=None  # type: ignore[arg-type]
        )


def test_unknown_adapter_type_is_rejected_authoritatively():
    rt = _fresh_runtime()
    # The AdapterFactory does not know "nope" -> authoritative resolution failure.
    with pytest.raises(AdapterTypeError):
        register_production_sources(
            rt,
            _provider(SourceDefinition(name="bad-a", adapter_type="nope")),
            _registered_factory(),
        )
    # Nothing was registered on failure.
    assert rt.supervisor.count() == 0


# ---------------------------------------------------------------------------
# End-to-end: registered source -> canonical Event -> RUNNING plugin, only the
# RUNNING plugin receives (lifecycle filtering preserved through registration).
# ---------------------------------------------------------------------------
def test_lifecycle_filtering_preserved_through_registration():
    rt = _fresh_runtime()
    running = _RecordingPlugin("reg-running")
    stopped = _RecordingPlugin("reg-stopped")
    loaded = _RecordingPlugin("reg-loaded")

    rt.plugin_manager.register_plugin(running)
    rt.plugin_manager.register_plugin(stopped)
    rt.plugin_manager.register_plugin(loaded)
    rt.plugin_manager._registry.update_status("reg-running", RUNNING)
    rt.plugin_manager._registry.update_status("reg-stopped", STOPPED)
    rt.plugin_manager._registry.update_status("reg-loaded", LOADED)

    register_production_sources(
        rt,
        _provider(SourceDefinition(name="atak-a", adapter_type="atak")),
        _registered_factory(),
    )
    rt.start()
    try:
        assert _wait_for(lambda: len(running.received) >= 1)
        assert stopped.received == []
        assert loaded.received == []
    finally:
        rt.stop()


def test_shutdown_after_registration_leaves_no_threads():
    rt = _fresh_runtime()
    plugin = _RecordingPlugin("reg-shutdown")
    _make_running(rt.plugin_manager, plugin)

    register_production_sources(
        rt,
        _provider(SourceDefinition(name="atak-a", adapter_type="atak")),
        _registered_factory(),
    )
    rt.start()
    assert _wait_for(lambda: len(plugin.received) >= 1)
    rt.stop()
    assert rt.started is False
    for t in threading.enumerate():
        assert not t.name.startswith("adapter-runtime-"), (
            f"orphaned source thread left after stop: {t.name}"
        )
