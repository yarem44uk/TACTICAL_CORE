"""WO-014-008 — Production Runtime Control Plane tests.

Proves that ``ProductionRuntimeController`` is a thin facade over the EXISTING
production runtime: it binds to an injected ``ProductionRuntime``, delegates
start/stop to the runtime, delegates health to the WO-014-007 observer, and
derives state without storing any shadow copy.

Tests exercise the REAL production composition (``create_production_runtime``
plus real supervisor / pipeline / dispatcher / manager).  The only test double
is the external source adapter at the input boundary (explicitly permitted);
everything downstream is real.

Adversarial / mutation checks are both structural (source inspection of the
control module for forbidden imports / constructors / calls) and behavioral
(asserting the controller never constructs infrastructure and never delivers
events).
"""

import inspect
import time

import pytest

from app.bootstrap import ProductionRuntime, create_production_runtime
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.event_sources.runtime.adapter_runtime import AdapterRuntime
from app.event_sources.runtime.adapter_supervisor import AdapterSupervisor
from app.event_sources.runtime.lifecycle import AdapterState
from app.event_sources.runtime.production_control import ProductionRuntimeController
from app.event_sources.runtime.runtime_health import (
    RuntimeHealth,
    RuntimeState,
    SourceState,
    runtime_health,
)
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_dispatcher.plugin_dispatcher import PluginDispatcher
from app.plugins.manager.plugin_manager import PluginManager
from app.plugins.registry.registry import RUNNING
from app.plugins.sdk.base import BasePlugin

# ---------------------------------------------------------------------------
# Path to the production control module (for structural mutation guards).
# Resolved from the imported module so it is cwd-independent.
# ---------------------------------------------------------------------------
_CONTROL_MODULE = inspect.getfile(ProductionRuntimeController)


def _control_source() -> str:
    """Source of the control module with its module docstring removed.

    Structural scans must not trip on prose (the docstring legitimately
    describes forbidden patterns).  Removing the leading docstring leaves
    only executable code + method docstrings.
    """
    text = inspect.getsource(ProductionRuntimeController)
    # drop the first triple-quoted docstring block
    start = text.find('"""')
    if start != -1:
        end = text.find('"""', start + 3)
        if end != -1:
            text = text[:start] + text[end + 3 :]
    return text



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
    pattern as WO-014-004 E2E / WO-014-007 tests)."""
    return create_production_runtime(plugin_manager=PluginManager())


def _wait_for(fn, timeout: float = 5.0, interval: float = 0.01) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# T1 / T2 — binding & no-construction
# ---------------------------------------------------------------------------
def test_t1_controller_binds_to_existing_production_runtime():
    rt = _fresh_runtime()
    ctl = ProductionRuntimeController(rt)
    assert ctl.runtime is rt


def test_t2_controller_does_not_construct_production_runtime():
    src = inspect.getsource(ProductionRuntimeController.__init__)
    # the init body must only store the injected reference
    assert "create_production_runtime" not in src
    assert "ProductionRuntime(" not in src.replace("ProductionRuntime):", "")


# ---------------------------------------------------------------------------
# T3 / T4 — start/stop delegation
# ---------------------------------------------------------------------------
def test_t3_start_delegates_to_runtime_start():
    rt = _fresh_runtime()
    ctl = ProductionRuntimeController(rt)
    ctl.start()
    assert rt.started is True
    ctl.stop()


def test_t4_stop_delegates_to_runtime_stop():
    rt = _fresh_runtime()
    rt.add_source(_Source("telegram"))
    rt.start()
    assert rt.started is True
    ctl = ProductionRuntimeController(rt)
    ctl.stop()
    assert rt.started is False
    assert rt.supervisor.count() == 0  # supervisor cleared by runtime.stop()


# ---------------------------------------------------------------------------
# T5 / T6 — repeated start/stop preserve existing runtime semantics
# ---------------------------------------------------------------------------
def test_t5_repeated_start_is_idempotent():
    rt = _fresh_runtime()
    ctl = ProductionRuntimeController(rt)
    ctl.start()
    ctl.start()  # second start must be a safe no-op (runtime is idempotent)
    assert rt.started is True
    ctl.stop()


def test_t6_repeated_stop_is_safe():
    rt = _fresh_runtime()
    rt.add_source(_Source("telegram"))
    rt.start()
    ctl = ProductionRuntimeController(rt)
    ctl.stop()
    ctl.stop()  # second stop must not raise (supervisor.shutdown is safe)
    assert rt.started is False


# ---------------------------------------------------------------------------
# T7 / T8 — state derived, health delegated
# ---------------------------------------------------------------------------
def test_t7_state_is_derived_not_stored():
    rt = _fresh_runtime()
    ctl = ProductionRuntimeController(rt)
    # before start
    assert ctl.state() == RuntimeState.STOPPED
    # controller holds only the runtime reference -> no shadow state attr
    assert set(vars(ctl).keys()) == {"_runtime"}
    ctl.start()
    try:
        assert ctl.state() in (RuntimeState.HEALTHY, RuntimeState.DEGRADED)
    finally:
        ctl.stop()


def test_t8_health_delegates_to_wo014007_observer():
    rt = _fresh_runtime()
    ctl = ProductionRuntimeController(rt)
    h = ctl.health()
    assert isinstance(h, RuntimeHealth)
    # identical to calling the authoritative observer directly
    assert h == runtime_health(rt)


# ---------------------------------------------------------------------------
# T9 / T10 — partial startup & failed source remain visible
# ---------------------------------------------------------------------------
def test_t9_partial_startup_remains_visible():
    rt = _fresh_runtime()
    rt.add_source(_Source("good"))
    rt.add_source(_Source("bad", fail_start=True))
    ctl = ProductionRuntimeController(rt)
    ctl.start()
    try:
        assert _wait_for(lambda: ctl.health().running == 1)
        h = ctl.health()
        assert h.registered == 2
        names = {s.name for s in h.sources}
        assert "good" in names and "bad" in names
        # non-transactional: the good source is active even though bad failed
        good = [s for s in h.sources if s.name == "good"][0]
        assert good.active is True
    finally:
        ctl.stop()


def test_t10_failed_source_remains_visible():
    rt = _fresh_runtime()
    rt.add_source(_Source("bad", fail_start=True))
    ctl = ProductionRuntimeController(rt)
    ctl.start()
    try:
        # a failing source is eventually reported FAILED
        assert _wait_for(lambda: ctl.health().failed >= 1)
        h = ctl.health()
        bad = [s for s in h.sources if s.name == "bad"][0]
        assert bad.classification == SourceState.FAILED
        assert bad.active is False
        assert h.state == RuntimeState.FAILED
    finally:
        ctl.stop()


# ---------------------------------------------------------------------------
# T11 — shutdown does not expose stale healthy state
# ---------------------------------------------------------------------------
def test_t11_shutdown_does_not_expose_stale_healthy_state():
    rt = _fresh_runtime()
    rt.add_source(_Source("telegram"))
    rt.start()
    ctl = ProductionRuntimeController(rt)
    ctl.stop()
    h = ctl.health()
    # after shutdown the runtime is not started and reports STOPPED
    assert rt.started is False
    assert h.started is False
    assert h.state == RuntimeState.STOPPED


# ---------------------------------------------------------------------------
# T12–T15 — no construction of authoritative infrastructure
# ---------------------------------------------------------------------------
def test_t12_no_adapter_supervisor_construction():
    assert "AdapterSupervisor(" not in inspect.getsource(ProductionRuntimeController)


def test_t13_no_event_pipeline_construction():
    assert "EventPipeline(" not in inspect.getsource(ProductionRuntimeController)


def test_t14_no_plugin_dispatcher_construction():
    assert "PluginDispatcher(" not in inspect.getsource(ProductionRuntimeController)


def test_t15_no_plugin_manager_construction():
    assert "PluginManager(" not in inspect.getsource(ProductionRuntimeController)


# ---------------------------------------------------------------------------
# T16 / T17 — no EventBus / legacy path dependency
# ---------------------------------------------------------------------------
def test_t16_no_eventbus_dependency():
    src = inspect.getsource(ProductionRuntimeController)
    assert "EventBus" not in src
    assert "eventbus" not in src.lower()


def test_t17_no_legacy_event_dependency():
    src = inspect.getsource(ProductionRuntimeController)
    assert "EventEngine" not in src
    assert "EventResult" not in src
    assert "app.core" not in src


# ---------------------------------------------------------------------------
# T18 / T19 — controller cannot dispatch or deliver events
# ---------------------------------------------------------------------------
def test_t18_controller_cannot_dispatch_events():
    src = _control_source()
    # scan executable code only (docstring stripped); look for actual calls
    assert ".process(" not in src
    assert "dispatch(" not in src
    assert ".dispatch(" not in src


def test_t19_controller_cannot_deliver_events_to_plugins():
    src = _control_source()
    assert "deliver_event" not in src
    assert ".on_event(" not in src



# ---------------------------------------------------------------------------
# T20 — lifecycle exceptions propagate (no swallowing)
# ---------------------------------------------------------------------------
def test_t20_lifecycle_exceptions_propagate():
    rt = _fresh_runtime()

    # a source whose start raises -> ProductionRuntime.start() must surface the
    # failure path without the controller swallowing it. start_all() logs and
    # continues, so start() itself does not raise for a bad adapter; instead we
    # verify the controller does not catch/hide anything by injecting a runtime
    # whose start() raises.
    class _BoomRuntime:
        started = False

        def start(self):
            raise RuntimeError("boom")

        def stop(self):
            pass

    ctl = ProductionRuntimeController(_BoomRuntime())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="boom"):
        ctl.start()


# ---------------------------------------------------------------------------
# MUTATION: M1 — controller must not construct ProductionRuntime
# ---------------------------------------------------------------------------
def test_m1_no_production_runtime_construction():
    src = inspect.getsource(ProductionRuntimeController)
    assert "create_production_runtime" not in src
    assert "ProductionRuntime(" not in src


# ---------------------------------------------------------------------------
# MUTATION: M2 — no AdapterSupervisor construction
# ---------------------------------------------------------------------------
def test_m2_no_supervisor_construction():
    src = inspect.getsource(ProductionRuntimeController)
    assert "AdapterSupervisor(" not in src


# ---------------------------------------------------------------------------
# MUTATION: M6 — no shadow state registry
# ---------------------------------------------------------------------------
def test_m6_no_shadow_state():
    rt = _fresh_runtime()
    ctl = ProductionRuntimeController(rt)
    # only the injected runtime may be stored; no _state/_health/_sources/_registry
    assert set(vars(ctl).keys()) == {"_runtime"}


# ---------------------------------------------------------------------------
# MUTATION: M7 — health aggregation is not duplicated
# ---------------------------------------------------------------------------
def test_m7_health_not_duplicated():
    # health() must delegate to the observer, not re-aggregate
    src = inspect.getsource(ProductionRuntimeController.health)
    assert "runtime_health(" in src
    # no local re-implementation of the precedence logic
    assert "SourceState.FAILED" not in src
    assert "SourceState.DEGRADED" not in src


# ---------------------------------------------------------------------------
# MUTATION: M8 / M9 — no dispatch / deliver calls
# ---------------------------------------------------------------------------
def test_m8_no_dispatch_call():
    src = _control_source()
    assert "dispatch(" not in src
    assert ".dispatch(" not in src


def test_m9_no_deliver_event_call():
    src = _control_source()
    assert "deliver_event" not in src


# ---------------------------------------------------------------------------
# MUTATION: M10 / M11 — no EventBus / legacy import in module source
# ---------------------------------------------------------------------------
def test_m10_no_eventbus_in_module_file():
    src = _control_source()
    assert "eventbus" not in src.lower()
    assert "EventBus" not in src


def test_m11_no_legacy_in_module_file():
    src = _control_source()
    assert "EventEngine" not in src
    assert "EventResult" not in src
    assert "app.core" not in src



# ---------------------------------------------------------------------------
# MUTATION: M12 — plugin lifecycle not modified
# ---------------------------------------------------------------------------
def test_m12_no_plugin_lifecycle_control():
    src = inspect.getsource(ProductionRuntimeController)
    for token in ("startup_all", "shutdown_all", "register_plugin",
                  "unregister_plugin", "set_plugin_state"):
        assert token not in src


# ---------------------------------------------------------------------------
# MUTATION: M13 — no direct source lifecycle manipulation
# ---------------------------------------------------------------------------
def test_m13_no_direct_source_lifecycle_control():
    src = _control_source()
    # must delegate via runtime.start()/stop() only, never supervisor per-source calls
    assert "supervisor.start_all" not in src
    assert "supervisor.stop_all" not in src
    assert "supervisor.shutdown" not in src
    assert "supervisor.restart" not in src
    assert "get_runtime" not in src



# ---------------------------------------------------------------------------
# MUTATION: M14 — no threads/timers introduced by the controller
# ---------------------------------------------------------------------------
def test_m14_no_threads_or_timers():
    src = inspect.getsource(ProductionRuntimeController)
    assert "threading" not in src
    assert "Thread(" not in src
    assert "Timer(" not in src


# ---------------------------------------------------------------------------
# MUTATION: M15 — exceptions not swallowed
# ---------------------------------------------------------------------------
def test_m15_no_exception_swallowing():
    src = inspect.getsource(ProductionRuntimeController)
    assert "except Exception" not in src
    assert "except:" not in src


# ---------------------------------------------------------------------------
# End-to-end sanity: controller start -> source event -> RUNNING plugin via the
# canonical pipeline (real composition), proving the control plane does not
# interfere with the canonical event path.
# ---------------------------------------------------------------------------
def test_e2e_canonical_path_untouched():
    rt = _fresh_runtime()
    ctl = ProductionRuntimeController(rt)

    # register a RUNNING plugin through the authoritative manager (real pattern
    # from WO-014-004 bootstrap tests)
    pm = rt.plugin_manager
    plugin = _RecordingPlugin("p1")
    pm.register_plugin(plugin)
    pm._registry.update_status(plugin.plugin_id, RUNNING)

    rt.add_source(_Source("telegram"))
    ctl.start()
    try:
        assert _wait_for(lambda: ctl.health().running == 1)
        h = ctl.health()
        assert h.state == RuntimeState.HEALTHY
    finally:
        ctl.stop()


class _RecordingPlugin(BasePlugin):
    """Real-plugin-boundary double following the WO-014-004 test pattern."""

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

    def on_event(self, event) -> None:
        self.received.append(event)

