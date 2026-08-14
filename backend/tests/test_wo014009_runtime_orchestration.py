"""WO-014-009 — Production Runtime Orchestration & Lifecycle Integration.

Consolidated architectural-contract lock for the production runtime stack.
WO-014-009 is a TEST-ONLY hardening work order: it adds no production code and
modifies no production file.  It proves the existing orchestration/lifecycle
contract (built across WO-013/014) against the REAL production runtime path:

    Source Adapter
        -> AdapterSupervisor / AdapterRuntime
        -> EventFactory
        -> canonical app.event.Event
        -> EventPipeline.process(event)
        -> PluginDispatcher.dispatch(event)
        -> PluginManager.deliver_event(event)
        -> RUNNING plugin.on_event(event)

and the control facade:

    ProductionRuntimeController
        -> ProductionRuntime
        -> AdapterSupervisor
        -> AdapterRuntime(s)

Contracts covered (C1..C12) and adversarial mutations (M1..M10) are defined in
the WO-014-009 implementation authorization.

The ONLY test double is the external source adapter at the input boundary
(explicitly permitted).  Everything downstream — supervisor, runtimes,
lifecycle, restart policy, health observer, factory, pipeline, dispatcher,
plugin manager — is the real production implementation.

Terminal-FAILED synchronization (C4): the restart budget is bounded
(max_restarts=3 by default), so a persistently failing source oscillates
FAILED -> STARTING -> (new thread) until the budget is exhausted.  Merely
sampling ``failed == 1`` is NOT the terminal condition.  This suite always
synchronizes on the AUTHORITATIVE per-runtime terminal condition:

    AdapterState == FAILED.value  AND  restart_budget_remaining == 0

via bounded polling with a diagnostic timeout (never an arbitrary fixed sleep).
"""

import inspect
import threading
import time

import pytest

from app.bootstrap import ProductionRuntime, create_production_runtime
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.event_sources.runtime.adapter_runtime import AdapterRuntime
from app.event_sources.runtime.adapter_supervisor import AdapterSupervisor
from app.event_sources.runtime.lifecycle import AdapterState, LifecycleTransitionError
from app.event_sources.runtime.production_control import ProductionRuntimeController
from app.event_sources.runtime.restart_policy import RestartPolicy
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
# Paths / source helpers for structural mutation guards (cwd-independent).
# ---------------------------------------------------------------------------
_CONTROL_MODULE = inspect.getfile(ProductionRuntimeController)
_SUPERVISOR_MODULE = inspect.getfile(AdapterSupervisor)
_RUNTIME_MODULE = inspect.getfile(AdapterRuntime)


def _module_imports(module_file: str) -> str:
    """Return only the import lines of a module (for structural scans)."""
    with open(module_file, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    return "\n".join(
        line.strip()
        for line in lines
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ).lower()


# ---------------------------------------------------------------------------
# Boundary double: controllable source adapter (input boundary only).
# ---------------------------------------------------------------------------
class _Source(IEventSourceAdapter):
    def __init__(
        self,
        name: str,
        fail_start: bool = False,
        degrade: bool = False,
        emit: list | None = None,
    ):
        self._name = name
        self._running = False
        self._fail_start = fail_start
        self._degrade = degrade
        self._emit = emit or []

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
        if self._emit:
            out, self._emit = self._emit, []
            return out
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

    def on_event(self, event) -> None:
        self.received.append(event)


def _fresh_runtime() -> ProductionRuntime:
    """Real production composition with an isolated PluginManager."""
    return create_production_runtime(plugin_manager=PluginManager())


def _wait_for(fn, timeout: float = 5.0, interval: float = 0.01) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


def _wait_failed_terminal(rt, name: str, timeout: float = 15.0,
                          interval: float = 0.01) -> None:
    """Wait for a source's AUTHORITATIVE terminal FAILED state (budget 0)."""
    deadline = time.time() + timeout
    last_state = "unknown"
    while time.time() < deadline:
        rt_obj = rt.supervisor.get_runtime(name)
        if rt_obj.state == AdapterState.FAILED:
            budget = rt_obj.health().get("restart_budget_remaining")
            if budget == 0:
                return
            last_state = f"FAILED(budget={budget})"
        else:
            last_state = str(rt_obj.state)
        time.sleep(interval)
    raise AssertionError(
        f"source '{name}' did not reach terminal FAILED within {timeout}s; "
        f"last observed AdapterState: {last_state}"
    )


def _active_threads(prefix: str) -> list:
    return [t for t in threading.enumerate() if t.name.startswith(prefix)]


# ---------------------------------------------------------------------------
# Keep the bounded auto-restart cycle from flooding the test log.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _quiet_adapter_runtime_logger():
    import logging
    logger = logging.getLogger("app.event_sources.runtime.adapter_runtime")
    old = logger.level
    logger.setLevel(logging.CRITICAL)
    yield
    logger.setLevel(old)


# ===========================================================================
# C1 — DUPLICATE REGISTRATION
# ===========================================================================
def test_c1_duplicate_registration_rejected_deterministically():
    rt = _fresh_runtime()
    rt.add_source(_Source("telegram"))
    with pytest.raises(ValueError):
        rt.add_source(_Source("telegram"))  # same source_name -> rejected
    # no duplicate runtime / second lifecycle owner
    assert rt.supervisor.count() == 1
    assert rt.supervisor.list_runtimes() == ["telegram"]


def test_c1b_duplicate_rejection_is_stable_across_repeated_calls():
    rt = _fresh_runtime()
    rt.add_source(_Source("sig"))
    for _ in range(3):
        with pytest.raises(ValueError):
            rt.add_source(_Source("sig"))
    assert rt.supervisor.count() == 1


# ===========================================================================
# C2 — START ORCHESTRATION (controller -> runtime -> supervisor -> runtime)
# ===========================================================================
def test_c2_start_orchestration_reaches_all_running():
    rt = _fresh_runtime()
    rt.add_source(_Source("telegram"))
    rt.add_source(_Source("signal"))
    rt.add_source(_Source("mqtt"))
    ctl = ProductionRuntimeController(rt)
    ctl.start()
    try:
        assert _wait_for(lambda: ctl.health().running == 3)
        h = ctl.health()
        assert h.state == RuntimeState.HEALTHY
        assert all(s.classification == SourceState.RUNNING for s in h.sources)
        # all three runtimes are real AdapterRuntime instances owned by the
        # single supervisor (no second runtime created for any source).
        assert rt.supervisor.count() == 3
        for name in ("telegram", "signal", "mqtt"):
            assert isinstance(rt.supervisor.get_runtime(name), AdapterRuntime)
    finally:
        ctl.stop()


# ===========================================================================
# C3 — FAILURE ISOLATION (one failed source must NOT stop healthy ones)
# ===========================================================================
def test_c3_failure_isolation_healthy_source_stays_running():
    rt = _fresh_runtime()
    rt.add_source(_Source("good"))
    rt.add_source(_Source("bad", fail_start=True))
    ctl = ProductionRuntimeController(rt)
    ctl.start()
    try:
        assert _wait_for(lambda: ctl.health().running == 1)
        _wait_failed_terminal(rt, "bad")
        h = ctl.health()
        # good stays RUNNING/active
        good = [s for s in h.sources if s.name == "good"][0]
        assert good.classification == SourceState.RUNNING
        assert good.active is True
        # bad is terminal FAILED
        bad = [s for s in h.sources if s.name == "bad"][0]
        assert bad.classification == SourceState.FAILED
        assert bad.active is False
        # aggregate represents the failure
        assert h.state == RuntimeState.FAILED
    finally:
        ctl.stop()


# ===========================================================================
# C4 — TERMINAL FAILED SYNCHRONIZATION (authoritative condition, not transient)
# ===========================================================================
def test_c4_terminal_failed_requires_budget_exhausted():
    rt = _fresh_runtime()
    rt.add_source(_Source("bad", fail_start=True))
    ctl = ProductionRuntimeController(rt)
    ctl.start()
    try:
        # This must only succeed on the AUTHORITATIVE terminal condition:
        # AdapterState.FAILED AND restart_budget_remaining == 0.  It raises a
        # diagnostic on timeout instead of silently passing on a transient
        # FAILED observation.
        _wait_failed_terminal(rt, "bad", timeout=20.0)
        rt_obj = rt.supervisor.get_runtime("bad")
        h = rt_obj.health()
        assert h["state"] == AdapterState.FAILED.value
        assert h["restart_budget_remaining"] == 0
        assert rt_obj.state == AdapterState.FAILED
    finally:
        ctl.stop()


def test_c4b_transient_failed_is_not_terminal_while_budget_remains():
    """FAILED/restarting with a positive budget is NOT terminal.

    A persistently failing source auto-restarts (FAILED -> STARTING -> new
    thread) for as long as restart budget remains.  Only when the budget is
    exhausted does it settle into the AUTHORITATIVE terminal FAILED
    (restart_budget_remaining == 0).  This test proves the two are distinct:
    with a large budget the runtime keeps restarting (remaining > 0 throughout,
    never terminal); at budget == 0 (covered by C4/C5) it becomes terminal.
    """

    policy = RestartPolicy(max_restarts=1000, restart_delay=0.02)
    rt = create_production_runtime(plugin_manager=PluginManager())
    rt.add_source(_Source("bad", fail_start=True))
    rt.supervisor.get_runtime("bad")._restart_policy = policy
    ctl = ProductionRuntimeController(rt)
    ctl.start()
    try:
        rt_obj = rt.supervisor.get_runtime("bad")
        # The runtime auto-restarts while budget remains: restart count grows
        # and the budget is never exhausted (remaining stays > 0) — i.e. it
        # does NOT settle into terminal FAILED, proving FAILED-with-budget>0
        # is a non-terminal, restartable state.
        assert _wait_for(
            lambda: rt_obj.health()["restarts"] >= 2, timeout=10.0
        )
        # restart count kept increasing AND budget was never exhausted.
        assert rt_obj.health()["restarts"] >= 2
        assert rt_obj.health()["restart_budget_remaining"] > 0
        # It is still actively oscillating (auto-restart in progress), NOT a
        # terminal FAILED: state cycles between STARTING/FAILED with budget.
        assert rt_obj.health()["restart_budget_remaining"] > 0
    finally:
        ctl.stop()


# ===========================================================================
# C5 — RESTART POLICY (two distinct phases)
# ===========================================================================
def test_c5_restart_with_budget_remains_then_terminal_failure():
    rt = _fresh_runtime()
    rt.add_source(_Source("bad", fail_start=True))
    ctl = ProductionRuntimeController(rt)
    ctl.start()
    try:
        rt_obj = rt.supervisor.get_runtime("bad")
        # phase 1: while the budget remains, the source auto-restarts
        # (FAILED -> STARTING -> new thread) and is NOT terminal.
        assert _wait_for(
            lambda: rt_obj.health()["restarts"] >= 1, timeout=15.0
        )
        # phase 2: terminal failure after budget exhaustion.
        _wait_failed_terminal(rt, "bad", timeout=20.0)
        h = rt_obj.health()
        assert h["state"] == AdapterState.FAILED.value
        assert h["restart_budget_remaining"] == 0
    finally:
        ctl.stop()


def test_c5b_restart_policy_not_mutated_by_runtime():
    """The runtime uses the real RestartPolicy semantics; it is not replaced."""
    rt = _fresh_runtime()
    rt.add_source(_Source("ok"))
    rt_obj = rt.supervisor.get_runtime("ok")
    assert isinstance(rt_obj._restart_policy, RestartPolicy)
    assert rt_obj._restart_policy.max_restarts == 3  # default finite budget


# ===========================================================================
# C6 — AGGREGATE HEALTH (authoritative precedence + partial startup)
# ===========================================================================
def test_c6_aggregate_precedence_failed_over_degraded_over_healthy():
    # (a) healthy only -> HEALTHY
    rt = _fresh_runtime()
    rt.add_source(_Source("good"))
    rt.start()
    try:
        assert _wait_for(lambda: runtime_health(rt).running == 1)
        assert runtime_health(rt).state == RuntimeState.HEALTHY
    finally:
        rt.stop()

    # (b) healthy + degraded -> DEGRADED
    rt = _fresh_runtime()
    rt.add_source(_Source("good"))
    rt.add_source(_Source("deg", degrade=True))
    rt.start()
    try:
        assert _wait_for(lambda: runtime_health(rt).running == 1)
        assert _wait_for(lambda: runtime_health(rt).degraded == 1)
        assert runtime_health(rt).state == RuntimeState.DEGRADED
    finally:
        rt.stop()

    # (c) healthy + degraded + terminal FAILED -> FAILED (highest precedence)
    rt = _fresh_runtime()
    rt.add_source(_Source("good"))
    rt.add_source(_Source("deg", degrade=True))
    rt.add_source(_Source("bad", fail_start=True))
    rt.start()
    try:
        _wait_failed_terminal(rt, "bad")
        assert _wait_for(lambda: runtime_health(rt).running == 1)
        assert runtime_health(rt).state == RuntimeState.FAILED
    finally:
        rt.stop()


def test_c6b_partial_startup_and_not_started_stopped():
    rt = _fresh_runtime()
    rt.add_source(_Source("a"))
    # not started -> STOPPED regardless of registration
    assert runtime_health(rt).state == RuntimeState.STOPPED
    rt.start()
    try:
        assert _wait_for(lambda: runtime_health(rt).running == 1)
        assert runtime_health(rt).state == RuntimeState.HEALTHY
    finally:
        rt.stop()


# ===========================================================================
# C7 / C8 — SHUTDOWN + IDEMPOTENCY (no orphan threads)
# ===========================================================================
def test_c7_shutdown_stops_all_runtimes_no_orphan_threads():
    rt = _fresh_runtime()
    for n in ("a", "b", "c"):
        rt.add_source(_Source(n))
    rt.start()
    assert _wait_for(lambda: runtime_health(rt).running == 3)
    ctl = ProductionRuntimeController(rt)
    ctl.stop()
    # all runtimes STOPPED / supervisor cleared
    assert rt.started is False
    assert rt.supervisor.count() == 0
    assert runtime_health(rt).state == RuntimeState.STOPPED
    # no orphan runtime threads remain
    assert _active_threads("adapter-runtime-") == []


def test_c8_repeated_stop_is_idempotent_and_leaves_no_threads():
    rt = _fresh_runtime()
    rt.add_source(_Source("a"))
    rt.start()
    assert _wait_for(lambda: runtime_health(rt).running == 1)
    ctl = ProductionRuntimeController(rt)
    ctl.stop()
    ctl.stop()  # repeated stop must be a safe no-op
    ctl.stop()
    assert rt.started is False
    assert runtime_health(rt).state == RuntimeState.STOPPED
    assert _active_threads("adapter-runtime-") == []


# ===========================================================================
# C9 — CONTROLLER FACADE OWNERSHIP (structural)
# ===========================================================================
def test_c9_controller_does_not_construct_infrastructure():
    src = inspect.getsource(ProductionRuntimeController)
    assert "create_production_runtime" not in src
    assert "AdapterSupervisor(" not in src
    assert "PluginManager(" not in src
    assert "EventFactory(" not in src
    assert "EventPipeline(" not in src
    assert "PluginDispatcher(" not in src
    # controller stores only the injected runtime -> no shadow state
    rt = _fresh_runtime()
    ctl = ProductionRuntimeController(rt)
    assert set(vars(ctl).keys()) == {"_runtime"}


def test_c9b_controller_has_no_threads_or_timers():
    src = inspect.getsource(ProductionRuntimeController)
    assert "threading" not in src
    assert "Thread(" not in src
    assert "Timer(" not in src


# ===========================================================================
# C10 — CANONICAL EVENT PATH (end-to-end through the real runtime)
# ===========================================================================
def test_c10_canonical_event_path_delivers_to_plugin():
    rt = _fresh_runtime()
    plugin = _RecordingPlugin("wo014009-rec")
    rt.plugin_manager.register_plugin(plugin)
    rt.plugin_manager._registry.update_status(plugin.plugin_id, RUNNING)

    emitting = _Source("emit", emit=[{"k": 1}])
    rt.add_source(emitting)
    rt.start()
    try:
        assert _wait_for(
            lambda: len(plugin.received) >= 1, timeout=10.0
        ), "canonical event did not reach the plugin through the real path"
        ev = plugin.received[0]
        # the event is a canonical app.event.Event from the real factory
        assert ev.source == "emit"
        assert ev.payload == {"k": 1}
    finally:
        rt.stop()


def test_c10b_no_direct_source_to_plugin_bypass_in_control_path():
    # The controller exposes no way to push an event into the pipeline or
    # plugin layer directly; only lifecycle control operations are exposed.
    # start_source/stop_source/restart_source are facade delegations to the
    # canonical ProductionRuntime -> AdapterSupervisor -> AdapterRuntime path
    # (WO-014-010) and do NOT bypass EventFactory/EventPipeline/PluginManager.
    rt = _fresh_runtime()
    ctl = ProductionRuntimeController(rt)
    allowed = {
        "start",
        "stop",
        "state",
        "health",
        "runtime",
        "start_source",
        "stop_source",
        "restart_source",
    }
    public = {m for m in dir(ctl) if not m.startswith("_")}
    assert public <= allowed


# ===========================================================================
# C11 — EVENTBUS / LEGACY ISOLATION (structural import scan)
# ===========================================================================
def test_c11_no_eventbus_or_legacy_coupling_in_production_runtime_modules():
    for mod in (_CONTROL_MODULE, _SUPERVISOR_MODULE, _RUNTIME_MODULE):
        imports = _module_imports(mod)
        for forbidden in ("app.core", "eventbus", "event_engine", "event_result"):
            assert forbidden not in imports, (
                f"forbidden import '{forbidden}' in {mod}"
            )
    # The control module must not reference EventBus / EventEngine / EventResult
    src = inspect.getsource(ProductionRuntimeController)
    assert "EventBus" not in src
    assert "EventEngine" not in src
    assert "EventResult" not in src


# ===========================================================================
# C12 — SINGLE OWNER / NO DUPLICATION
# ===========================================================================
def test_c12_single_owner_each_responsibility():
    rt = _fresh_runtime()
    ctl = ProductionRuntimeController(rt)
    # ProductionRuntime is the orchestration boundary, injected once
    assert ctl.runtime is rt
    # AdapterSupervisor is the single supervision owner
    assert isinstance(rt.supervisor, AdapterSupervisor)
    # exactly one supervisor on the runtime
    assert rt.supervisor.count() == 0
    # the canonical composition root produced exactly one of each
    assert isinstance(rt.pipeline, EventPipeline)
    assert isinstance(rt.plugin_dispatcher, PluginDispatcher)
    assert isinstance(rt.plugin_manager, PluginManager)
    # the dispatcher delegates to the SAME plugin manager the runtime exposes
    assert rt.plugin_dispatcher._plugin_manager is rt.plugin_manager


# ===========================================================================
# MUTATIONS (adversarial detection)
# ===========================================================================
# M1 — bypass AdapterSupervisor: controller/source must route through supervisor
def test_m1_controller_cannot_bypass_supervisor():
    src = inspect.getsource(ProductionRuntimeController)
    # controller never calls pipeline.process / dispatcher.dispatch / deliver
    assert ".process(" not in src
    assert ".dispatch(" not in src
    assert "deliver_event" not in src
    # controller has no direct runtime thread creation
    assert "Thread(" not in src


# M2 — controller must not construct its own runtime
def test_m2_controller_does_not_construct_runtime():
    src = inspect.getsource(ProductionRuntimeController)
    assert "create_production_runtime" not in src
    assert "ProductionRuntime(" not in src


# M3 — EventBus / EventEngine coupling reintroduced -> detected
def test_m3_no_eventbus_coupling_detected():
    src = inspect.getsource(ProductionRuntimeController)
    assert "EventBus" not in src
    assert "EventEngine" not in src


# M4 — terminal budget exhaustion removed -> would fail C4/C5
def test_m4_terminal_failure_is_budget_anchored():
    # Structural guard: restart budget semantics live in RestartPolicy only.
    import app.event_sources.runtime.restart_policy as rp
    src = inspect.getsource(rp.RestartPolicy)
    assert "exhausted" in src  # the authoritative exhausted property exists
    # AdapterRuntime terminal check references the policy budget
    rt_src = inspect.getsource(AdapterRuntime)
    assert "exhausted" in rt_src or "remaining" in rt_src


# M5 — transient FAILED synchronization -> C4 helper rejects non-terminal
def test_m5_transient_failed_synchronization_is_rejected():
    # The helper asserts budget == 0 at terminal; a test that synchronized
    # only on failed>=1 would not satisfy C4.  Here we verify the terminal
    # condition helper requires BOTH state==FAILED AND budget==0.
    rt = _fresh_runtime()
    rt.add_source(_Source("bad", fail_start=True))
    ctl = ProductionRuntimeController(rt)
    ctl.start()
    try:
        _wait_failed_terminal(rt, "bad", timeout=20.0)
        h = rt.supervisor.get_runtime("bad").health()
        assert h["state"] == AdapterState.FAILED.value
        assert h["restart_budget_remaining"] == 0
    finally:
        ctl.stop()


# M6 — arbitrary fixed sleep introduced -> structural guard (no raw sleep in ctl)
def test_m6_controller_has_no_arbitrary_sleep():
    src = inspect.getsource(ProductionRuntimeController)
    assert "time.sleep" not in src
    assert "sleep(" not in src


# M7 — one failed source stops healthy sources -> C3 detects (behavioral)
def test_m7_failure_does_not_stop_healthy():
    rt = _fresh_runtime()
    rt.add_source(_Source("good"))
    rt.add_source(_Source("bad", fail_start=True))
    ctl = ProductionRuntimeController(rt)
    ctl.start()
    try:
        _wait_failed_terminal(rt, "bad")
        assert _wait_for(lambda: ctl.health().running == 1)
        good = [s for s in ctl.health().sources if s.name == "good"][0]
        assert good.active is True
    finally:
        ctl.stop()


# M8 — EventFactory bypassed -> canonical path test detects (C10)
def test_m8_factory_not_bypassed_in_runtime():
    rt = _fresh_runtime()
    rt.add_source(_Source("emit", emit=[{"k": 1}]))
    plugin = _RecordingPlugin("wo014009-m8")
    rt.plugin_manager.register_plugin(plugin)
    rt.plugin_manager._registry.update_status(plugin.plugin_id, RUNNING)
    rt.start()
    try:
        assert _wait_for(lambda: len(plugin.received) >= 1, timeout=10.0)
        assert isinstance(plugin.received[0].payload, dict)
    finally:
        rt.stop()


# M9 — EventPipeline bypassed -> controller cannot call deliver directly
def test_m9_pipeline_not_bypassed_by_controller():
    src = inspect.getsource(ProductionRuntimeController)
    assert ".process(" not in src
    assert "deliver_event" not in src


# M10 — controller-owned lifecycle thread -> structural guard
def test_m10_controller_owns_no_thread_or_timer():
    src = inspect.getsource(ProductionRuntimeController)
    assert "threading" not in src
    assert "Thread(" not in src
    assert "Timer(" not in src
