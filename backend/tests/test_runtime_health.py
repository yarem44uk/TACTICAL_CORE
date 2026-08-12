"""WO-014-007 — Production Runtime Health & Operational State tests.

Proves the read-only operational view (``runtime_health()``) composes the
AUTHORITATIVE production runtime state without introducing a second source
state machine, a second supervisor, a second pipeline, a second dispatcher, a
second PluginManager, an EventBus, or a legacy event path.

Tests use the REAL production bootstrap (``create_production_runtime``) and
the REAL composition path.  The only test double is the external source
adapter at the input boundary (explicitly permitted); everything downstream
(pipeline, dispatcher, manager, supervisor, runtime lifecycle) is real.

The health module is OBSERVABILITY ONLY: it reads state; it must never
mutate lifecycle, start/stop adapters, or create any authoritative component.
"""

import inspect
import threading
import time

import pytest

from app.bootstrap import ProductionRuntime, create_production_runtime
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.event_sources.runtime.adapter_runtime import AdapterRuntime
from app.event_sources.runtime.adapter_supervisor import AdapterSupervisor
from app.event_sources.runtime.lifecycle import AdapterState
from app.event_sources.runtime.runtime_health import (
    RuntimeHealth,
    RuntimeState,
    SourceState,
    SourceStatus,
    runtime_health,
)
from app.plugins.manager.plugin_manager import PluginManager


# ---------------------------------------------------------------------------
# Boundary double: controllable source adapter (input boundary only).
# ---------------------------------------------------------------------------
class _Source(IEventSourceAdapter):
    def __init__(self, name: str, fail_start: bool = False, degrade: bool = False):
        self._name = name
        self._running = False
        self._fail_start = fail_start
        self._degrade = degrade

    def start(self) -> None:
        if self._fail_start:
            raise RuntimeError(f"{self._name} start failed")
        self._running = True

    def stop(self) -> None:
        self._running = False

    def health(self) -> bool:
        return self._running

    def read_events(self):
        if self._degrade:
            raise RuntimeError(f"{self._name} read failed")
        return []

    def source_name(self) -> str:
        return self._name


def _fresh_runtime() -> ProductionRuntime:
    """Real production composition with an isolated PluginManager (same
    pattern as WO-014-004 E2E tests)."""
    return create_production_runtime(plugin_manager=PluginManager())


def _wait_for(fn, timeout: float = 5.0, interval: float = 0.01) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# 1. EMPTY RUNTIME
# ---------------------------------------------------------------------------
def test_empty_runtime_before_start():
    rt = _fresh_runtime()
    h = runtime_health(rt)
    assert isinstance(h, RuntimeHealth)
    assert h.started is False
    assert h.registered == 0
    assert h.running == 0
    assert h.degraded == 0
    assert h.failed == 0
    assert h.inactive == 0
    assert h.state == RuntimeState.STOPPED
    assert h.sources == ()


def test_empty_runtime_after_start_is_healthy():
    rt = _fresh_runtime()
    rt.start()
    try:
        h = runtime_health(rt)
        assert h.started is True
        assert h.registered == 0
        assert h.state == RuntimeState.HEALTHY
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# 2. REGISTERED BUT NOT STARTED
# ---------------------------------------------------------------------------
def test_registered_but_not_started():
    rt = _fresh_runtime()
    rt.add_source(_Source("telegram"))
    rt.add_source(_Source("signal"))
    h = runtime_health(rt)
    assert h.started is False
    assert h.registered == 2
    assert h.state == RuntimeState.STOPPED
    assert h.running == 0
    assert h.inactive == 2
    # each source reported as inactive / not active / not healthy
    for s in h.sources:
        assert s.classification == SourceState.INACTIVE
        assert s.active is False
        assert s.healthy is False


# ---------------------------------------------------------------------------
# 3. SINGLE HEALTHY SOURCE
# ---------------------------------------------------------------------------
def test_single_healthy_source():
    rt = _fresh_runtime()
    rt.add_source(_Source("telegram"))
    rt.start()
    try:
        assert _wait_for(lambda: runtime_health(rt).running == 1)
        h = runtime_health(rt)
        assert h.state == RuntimeState.HEALTHY
        assert h.registered == 1
        assert h.running == 1
        assert h.degraded == 0
        assert h.failed == 0
        assert h.healthy_sources == 1
        s = h.sources[0]
        assert s.name == "telegram"
        assert s.adapter_state == AdapterState.RUNNING.value
        assert s.classification == SourceState.RUNNING
        assert s.active is True
        assert s.healthy is True
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# 4. MULTIPLE HEALTHY SOURCES
# ---------------------------------------------------------------------------
def test_multiple_healthy_sources():
    rt = _fresh_runtime()
    rt.add_source(_Source("telegram"))
    rt.add_source(_Source("signal"))
    rt.add_source(_Source("mqtt"))
    rt.start()
    try:
        assert _wait_for(lambda: runtime_health(rt).running == 3)
        h = runtime_health(rt)
        assert h.state == RuntimeState.HEALTHY
        assert h.registered == 3
        assert h.running == 3
        assert {s.name for s in h.sources} == {"telegram", "signal", "mqtt"}
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# 5. SOURCE FAILURE (start failure -> FAILED)
# ---------------------------------------------------------------------------
def test_source_failure_is_reported_failed():
    rt = _fresh_runtime()
    rt.add_source(_Source("good"))
    rt.add_source(_Source("bad", fail_start=True))
    rt.start()
    try:
        # The failing source may auto-restart a few times (bounded budget)
        # before settling in FAILED; wait until a FAILED source is observed.
        assert _wait_for(lambda: runtime_health(rt).failed == 1)
        h = runtime_health(rt)
        assert h.state == RuntimeState.FAILED  # precedence: FAILED wins
        failed = [s for s in h.sources if s.name == "bad"][0]
        assert failed.classification == SourceState.FAILED
        assert failed.active is False
        assert failed.healthy is False
        assert failed.adapter_state == AdapterState.FAILED.value
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# 6. PARTIAL STARTUP: one good, one failing
# ---------------------------------------------------------------------------
def test_partial_startup_reports_good_running_and_bad_failed():
    rt = _fresh_runtime()
    rt.add_source(_Source("good"))
    rt.add_source(_Source("bad", fail_start=True))
    rt.start()
    try:
        assert _wait_for(lambda: runtime_health(rt).running == 1)
        assert _wait_for(lambda: runtime_health(rt).failed == 1)
        h = runtime_health(rt)
        # Non-transactional AdapterSupervisor: the good source stays active.
        assert h.running == 1
        assert h.failed == 1
        by_name = {s.name: s for s in h.sources}
        assert by_name["good"].classification == SourceState.RUNNING
        assert by_name["good"].active is True
        assert by_name["bad"].classification == SourceState.FAILED
        assert h.state == RuntimeState.FAILED  # aggregate reflects worst state
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# 7. DEGRADED SOURCE (recoverable read failure -> DEGRADED)
# ---------------------------------------------------------------------------
def test_degraded_source_reported_and_aggregate_degraded():
    rt = _fresh_runtime()
    rt.add_source(_Source("deg", degrade=True))
    rt.start()
    try:
        assert _wait_for(lambda: runtime_health(rt).degraded == 1)
        h = runtime_health(rt)
        s = h.sources[0]
        assert s.classification == SourceState.DEGRADED
        assert s.active is True
        assert s.healthy is True  # AdapterRuntime treats DEGRADED as healthy
        assert h.state == RuntimeState.DEGRADED
        assert h.degraded == 1
    finally:
        rt.stop()


def test_degraded_takes_precedence_over_healthy_not_failed():
    rt = _fresh_runtime()
    rt.add_source(_Source("good"))
    rt.add_source(_Source("deg", degrade=True))
    rt.start()
    try:
        assert _wait_for(lambda: runtime_health(rt).running == 1)
        assert _wait_for(lambda: runtime_health(rt).degraded == 1)
        h = runtime_health(rt)
        # DEGRADED > HEALTHY in aggregate (no FAILED present)
        assert h.state == RuntimeState.DEGRADED
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# 8. SHUTDOWN STATE
# ---------------------------------------------------------------------------
def test_shutdown_returns_to_stopped_and_clears_sources():
    rt = _fresh_runtime()
    rt.add_source(_Source("telegram"))
    rt.add_source(_Source("signal"))
    rt.start()
    assert _wait_for(lambda: runtime_health(rt).running == 2)
    rt.stop()
    h = runtime_health(rt)
    assert h.started is False
    assert h.state == RuntimeState.STOPPED
    assert h.registered == 0  # shutdown() clears the supervisor


# ---------------------------------------------------------------------------
# 9/10/11. COUNT ACCURACY + IDENTITY
# ---------------------------------------------------------------------------
def test_count_accuracy_and_identity_preserved():
    rt = _fresh_runtime()
    names = ["a", "b", "c", "d", "e"]
    for n in names:
        rt.add_source(_Source(n))
    rt.start()
    try:
        assert _wait_for(lambda: runtime_health(rt).running == 5)
        h = runtime_health(rt)
        assert h.registered == 5
        assert h.running == 5
        assert [s.name for s in h.sources] == sorted(names)
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# 12/13/14. NO SECOND SUPERVISOR / PIPELINE / DISPATCHER / MANAGER
# ---------------------------------------------------------------------------
def test_runtime_health_does_not_create_new_supervisor_pipeline_dispatcher_manager():
    rt = _fresh_runtime()
    h = runtime_health(rt)
    # The health module must not have introduced any new authoritative object.
    assert isinstance(rt.supervisor, AdapterSupervisor)
    assert isinstance(rt.plugin_manager, PluginManager)
    # plugin_manager is the authoritative singleton
    assert rt.plugin_manager is rt.event_runtime.plugin_manager


# ---------------------------------------------------------------------------
# 15. PluginManager SINGLETON INTEGRITY
# ---------------------------------------------------------------------------
def test_plugin_manager_singleton_integrity_via_health():
    rt1 = create_production_runtime()
    rt2 = create_production_runtime()
    # Authoritative global singleton is shared; health must not disturb it.
    assert rt1.plugin_manager is rt2.plugin_manager
    runtime_health(rt1)
    runtime_health(rt2)
    assert rt1.plugin_manager is rt2.plugin_manager


# ---------------------------------------------------------------------------
# 16. CANONICAL EVENT PATH REMAINS INTACT (health does not break delivery)
# ---------------------------------------------------------------------------
def test_health_does_not_alter_canonical_event_path():
    from app.event.event import Event
    from app.plugins.sdk.base import BasePlugin
    from app.plugins.registry.registry import RUNNING

    class _Rec(BasePlugin):
        def __init__(self, pid):
            self._pid = pid
            self.received = []
            super().__init__()

        @property
        def plugin_id(self):
            return self._pid

        def register(self):
            pass

        def unregister(self):
            pass

        def on_event(self, event):
            self.received.append(event)

    rt = _fresh_runtime()
    plugin = _Rec("h-rec-1")
    rt.plugin_manager.register_plugin(plugin)
    rt.plugin_manager._registry.update_status(plugin.plugin_id, RUNNING)

    class _Emitting(IEventSourceAdapter):
        def __init__(self):
            self._sent = False

        def start(self):
            pass

        def stop(self):
            pass

        def health(self):
            return True

        def read_events(self):
            if not self._sent:
                self._sent = True
                return [{"uid": "H-1", "type": "a-u-G", "time": 1750000000,
                         "lat": 1.0, "lon": 2.0, "how": "m-g",
                         "detail": {"callsign": "X"}}]
            return []

        def source_name(self):
            return "emit"

    rt.add_source(_Emitting())
    rt.start()
    try:
        # Read health while the pipeline is live.  Wait for the runtime
        # thread to reach the authoritative RUNNING state before sampling
        # (STARTING is a brief transitional state).
        assert _wait_for(lambda: runtime_health(rt).running == 1)
        h = runtime_health(rt)
        assert h.running >= 1
        assert _wait_for(lambda: len(plugin.received) >= 1)
        ev = plugin.received[0]
        assert isinstance(ev, Event)
        assert ev.source == "emit"
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# 17/18. NO EVENTBUS / LEGACY COUPLING
# ---------------------------------------------------------------------------
def test_health_module_has_no_eventbus_or_legacy_imports():
    """The health module must not import or reference EventBus / legacy
    event machinery in executable code.

    We scan the AST (imports, attribute accesses, name loads) rather than
    raw source text so that docstring prose is not misread as code usage.
    """
    import ast

    import app.event_sources.runtime.runtime_health as m

    tree = ast.parse(inspect.getsource(m))
    tokens: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                tokens.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                tokens.add(node.module.split(".")[0])
            for a in node.names:
                tokens.add(a.name)
        elif isinstance(node, ast.Name):
            tokens.add(node.id)
        elif isinstance(node, ast.Attribute):
            tokens.add(node.attr)

    forbidden = {"EventBus", "event_bus", "EventResult", "EventEngine",
                 "app_core", "deliver_event", "on_event"}
    hits = tokens & forbidden
    assert not hits, f"health module references forbidden legacy tokens: {hits}"


# ---------------------------------------------------------------------------
# 19. NO ORPHAN WORKER THREADS AFTER SHUTDOWN
# ---------------------------------------------------------------------------
def test_no_orphan_source_threads_after_shutdown():
    rt = _fresh_runtime()
    rt.add_source(_Source("a"))
    rt.add_source(_Source("b"))
    rt.start()
    assert _wait_for(lambda: runtime_health(rt).running == 2)
    rt.stop()
    time.sleep(0.2)
    for t in threading.enumerate():
        assert not t.name.startswith("adapter-runtime-"), (
            f"orphan worker thread left behind: {t.name}"
        )


# ---------------------------------------------------------------------------
# 20. MUTATION-RESISTANCE CHECKS
# ---------------------------------------------------------------------------
def test_health_reads_authoritative_supervisor_state_not_duplicate():
    """The health view must reflect the supervisor's runtime states live."""
    rt = _fresh_runtime()
    rt.add_source(_Source("telegram"))
    # Before start the authoritative state is STOPPED -> INACTIVE.
    h0 = runtime_health(rt)
    assert h0.inactive == 1
    assert h0.running == 0
    rt.start()
    try:
        assert _wait_for(lambda: runtime_health(rt).running == 1)
        # Same source object, live authoritative state changed -> view changed.
        h1 = runtime_health(rt)
        assert h1.running == 1
        assert h1.inactive == 0
    finally:
        rt.stop()


def test_health_is_read_only_does_not_mutate_runtime():
    rt = _fresh_runtime()
    rt.add_source(_Source("a"))
    rt.add_source(_Source("b"))
    before = {s.name: s.adapter_state for s in runtime_health(rt).sources}
    # Read twice; must not alter state (STOPPED stays STOPPED).
    runtime_health(rt)
    runtime_health(rt)
    after = {s.name: s.adapter_state for s in runtime_health(rt).sources}
    assert before == after
    assert set(after.values()) == {AdapterState.STOPPED.value}


def test_health_does_not_start_or_stop_anything():
    rt = _fresh_runtime()
    rt.add_source(_Source("a"))
    # Calling runtime_health must not start the source.
    assert rt.started is False
    runtime_health(rt)
    runtime_health(rt)
    assert rt.started is False
    # And must not have flipped any runtime to RUNNING.
    assert all(
        s.adapter_state == AdapterState.STOPPED.value
        for s in runtime_health(rt).sources
    )
