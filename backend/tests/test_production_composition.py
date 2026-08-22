"""WO-014-003 — Production Composition / Runtime Bootstrap E2E tests.

Proves the REAL production composition root assembled by
``app.composition.create_event_runtime`` delivers canonical Events to
registered + RUNNING plugins over the complete path:

    canonical app.event.Event
        |
        v
    EventPipeline.process(event)
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

These tests do NOT build the wiring themselves.  They call the production
composition function ``create_event_runtime()`` — the single authoritative
composition root — and assert on the resulting wired runtime.  No test
double is used for the pipeline, dispatcher, manager or plugin.
"""

import inspect
import sys

import pytest

import app.database.session as session_mod
from app.composition import EventRuntime, create_event_runtime
from app.database.session import configure_session_manager
from app.event.event import Event
from app.contracts.plugin import IPlugin
from app.plugins.sdk.base import BasePlugin
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
        event_id="evt-composition-0001",
        entity_id="entity-1",
        source="atak",
        payload={"lat": 50.0, "lon": 30.0},
    )


def _register_running(manager, plugin) -> None:
    manager.register_plugin(plugin)
    manager._registry.update_status(plugin.plugin_id, RUNNING)


@pytest.fixture()
def global_session_manager():
    """Configure the GLOBAL DatabaseSessionManager to an isolated in-memory
    SQLite database (exactly as the production app does at startup), create
    the durable canonical table, and reset afterwards so nothing leaks.

    WO-014-020: production composition now wires the durable canonical
    repository into the EventPipeline persistence seam, so
    ``pipeline.process(event)`` durably persists. These tests configure the
    existing global session manager (no second DB owner) and initialize the
    durable table so the wired pipeline persists exactly as in production.
    """
    from app.event_repository.durable.sqlalchemy_event_repository import (
        SQLAlchemyEventRepository,
    )

    manager = configure_session_manager("sqlite:///:memory:")
    SQLAlchemyEventRepository().initialize()
    yield manager
    session_mod._session_manager = None


# T1 — Production composition exists
def test_production_composition_creates_wired_runtime(global_session_manager):
    runtime = create_event_runtime()

    assert isinstance(runtime, EventRuntime)
    assert isinstance(runtime.pipeline, EventPipeline)
    assert isinstance(runtime.plugin_dispatcher, PluginDispatcher)


# T2 — Dispatcher attached to the pipeline by production composition
def test_production_composition_attaches_dispatcher(global_session_manager):
    runtime = create_event_runtime()
    # The dispatcher must be reachable through the pipeline's public
    # dispatcher slot after production composition.
    assert runtime.pipeline._dispatcher is runtime.plugin_dispatcher


# T3 — Canonical Event delivery reaches the plugin layer
def test_canonical_event_reaches_running_plugin(global_session_manager):
    runtime = create_event_runtime()
    plugin = _RecordingPlugin("c-1")
    _register_running(runtime.plugin_manager, plugin)

    event = _make_event()
    result = runtime.pipeline.process(event)

    assert result is True
    assert len(plugin.received) == 1
    # WO-030 — canonical identity contract: the durable path delivers a
    # canonical app.event.Event with the SAME event_id.  Object identity
    # (`is`) is not a durable architecture invariant.
    assert isinstance(plugin.received[0], Event)
    assert plugin.received[0].event_id == event.event_id


# T4 — Event identity preserved through the full composition
def test_event_identity_is_preserved(global_session_manager):
    runtime = create_event_runtime()
    plugin = _RecordingPlugin("c-ident")
    _register_running(runtime.plugin_manager, plugin)

    event = _make_event()
    runtime.pipeline.process(event)

    assert isinstance(plugin.received[0], Event)
    assert plugin.received[0].event_id == event.event_id


# T5 — RUNNING lifecycle filtering through production composition
def test_only_running_plugins_receive_event(global_session_manager):
    runtime = create_event_runtime()

    running = _RecordingPlugin("c-running")
    stopped = _RecordingPlugin("c-stopped")
    loaded = _RecordingPlugin("c-loaded")

    runtime.plugin_manager.register_plugin(running)
    runtime.plugin_manager.register_plugin(stopped)
    runtime.plugin_manager.register_plugin(loaded)
    runtime.plugin_manager._registry.update_status("c-running", RUNNING)
    runtime.plugin_manager._registry.update_status("c-stopped", STOPPED)
    runtime.plugin_manager._registry.update_status("c-loaded", LOADED)

    event = _make_event()
    runtime.pipeline.process(event)

    assert len(running.received) == 1
    assert isinstance(running.received[0], Event)
    assert running.received[0].event_id == event.event_id
    assert stopped.received == []
    assert loaded.received == []


# T6 — Failure isolation preserved through production composition
def test_failing_plugin_does_not_block_other_plugins(global_session_manager):
    runtime = create_event_runtime()

    failing = _FailingPlugin("c-fail")
    recording = _RecordingPlugin("c-ok")

    _register_running(runtime.plugin_manager, failing)
    _register_running(runtime.plugin_manager, recording)

    event = _make_event()
    runtime.pipeline.process(event)

    assert len(recording.received) == 1
    assert isinstance(recording.received[0], Event)
    assert recording.received[0].event_id == event.event_id


# T7 — Raw dict rejected at the canonical boundary
def test_raw_dict_is_rejected(global_session_manager):
    runtime = create_event_runtime()
    plugin = _RecordingPlugin("c-dict")
    _register_running(runtime.plugin_manager, plugin)

    with pytest.raises(TypeError):
        runtime.pipeline.process({})  # type: ignore[arg-type]

    assert plugin.received == []


# T8 — Legacy isolation: composition introduces no app.core / legacy EventBus
# coupling. WO-015 wires the CANONICAL EventBus (app.event_bus.event_bus) into
# production composition, so the guard forbids legacy app.core coupling while
# explicitly asserting the canonical event-bus + observation migration wiring.
def test_production_composition_has_no_legacy_coupling():
    import app.composition as composition

    imports = [
        line.strip()
        for line in inspect.getsource(sys.modules[composition.__name__]).splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]
    joined = "\n".join(imports).lower()

    # Forbidden: legacy app.core coupling and legacy event-result coupling.
    # The canonical event bus lives under app.event_bus (NOT app.core), so
    # "app.core" is the authoritative legacy-coupling token.
    for forbidden in ("app.core", "event_result", "eventresult"):
        assert forbidden not in joined, f"forbidden import found: {forbidden}"

    # The composition must import the canonical Event / pipeline / dispatcher.
    assert "from app.event_pipeline.event_pipeline import eventpipeline" in joined
    assert "from app.event_dispatcher.plugin_dispatcher import plugindispatcher" in joined

    # WO-015 — composition must import the CANONICAL event bus and the
    # ObservationService (not the legacy app.core EventBus).
    assert "from app.event_bus.event_bus import eventbus" in joined
    assert "from app.observation.service import observationservice" in joined


# T9 — No duplicate delivery for a single canonical Event
def test_no_duplicate_delivery(global_session_manager):
    runtime = create_event_runtime()
    plugin = _RecordingPlugin("c-single")
    _register_running(runtime.plugin_manager, plugin)

    event = _make_event()
    runtime.pipeline.process(event)

    assert len(plugin.received) == 1


# T10 — Existing plugin without custom on_event remains compatible
def test_existing_plugin_without_on_event_override_is_compatible(global_session_manager):
    runtime = create_event_runtime()

    # BasePlugin provides a no-op on_event; a plugin that does not override
    # it must remain instantiable and must not break delivery to others.
    class _NoOverridePlugin(BasePlugin):
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

    plain = _NoOverridePlugin("c-plain")
    recording = _RecordingPlugin("c-ok2")
    _register_running(runtime.plugin_manager, plain)
    _register_running(runtime.plugin_manager, recording)

    event = _make_event()
    runtime.pipeline.process(event)

    assert len(recording.received) == 1
    assert isinstance(recording.received[0], Event)
    assert recording.received[0].event_id == event.event_id
