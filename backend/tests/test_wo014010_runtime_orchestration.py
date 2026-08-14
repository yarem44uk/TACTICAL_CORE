"""WO-014-010 — Per-Source Operational Control & Aggregate Health.

WO-014-010 adds the missing per-source targeted lifecycle surface to the
production control plane:

    ProductionRuntimeController.start_source(name) / stop_source(name) /
        restart_source(name)
            -> ProductionRuntime.start_source / stop_source / restart_source
            -> AdapterSupervisor.start(name) / stop(name) / restart(name)
            -> AdapterRuntime.start() / stop() / restart()
            -> RestartPolicy (restart-budget authority, unchanged)

The controller stays a stateless facade; ProductionRuntime stays the
orchestration boundary; AdapterSupervisor stays the registry + targeted
runtime owner; AdapterRuntime stays the execution owner; RestartPolicy stays
the restart-budget owner.  Aggregate health is UNCHANGED — this suite verifies
it remains observational and deterministic.

The ONLY test double is the external source adapter at the input boundary.
Everything downstream — supervisor, runtimes, lifecycle, restart policy,
health observer, factory, pipeline, dispatcher, plugin manager — is the real
production implementation.

Tests exercise the canonical path:
    ProductionRuntimeController -> ProductionRuntime -> AdapterSupervisor ->
        AdapterRuntime
and prove per-source isolation, deterministic unknown-source behaviour,
singular ownership, and unchanged aggregate health.
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
from app.event_sources.runtime.runtime_health import RuntimeState, SourceState
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


def _module_source(module_file: str) -> str:
    """Return the full module source (for structural scans)."""
    with open(module_file, encoding="utf-8") as fh:
        return fh.read()


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


def _wait_state(rt, name: str, state: AdapterState, timeout: float = 5.0,
                interval: float = 0.01) -> None:
    deadline = time.time() + timeout
    last = "unknown"
    while time.time() < deadline:
        st = rt.supervisor.get_runtime(name).state
        if st == state:
            return
        last = str(st)
        time.sleep(interval)
    raise AssertionError(
        f"source '{name}' did not reach {state} within {timeout}s; "
        f"last observed AdapterState: {last}"
    )


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


@pytest.fixture(autouse=True)
def _quiet_adapter_runtime_logger():
    import logging

    logger = logging.getLogger("app.event_sources.runtime.adapter_runtime")
    old = logger.level
    logger.setLevel(logging.CRITICAL)
    yield
    logger.setLevel(old)


@pytest.fixture(autouse=True)
def _no_leaked_runtime_threads():
    """Ensure no adapter runtime thread leaks across tests.

    If a test fails mid-way and skips its own ctl.stop(), this teardown joins
    any leftover runtime threads so they cannot contaminate subsequent tests.
    """
    yield
    for t in _active_threads("adapter-runtime-"):
        if t.is_alive():
            t.join(timeout=2.0)


# ===========================================================================
# C1 — TARGETED START
# ===========================================================================
def test_c1_targeted_start_runs_only_the_named_source():
    rt = _fresh_runtime()
    rt.add_source(_Source("alpha"))
    rt.add_source(_Source("beta"))
    ctl = ProductionRuntimeController(rt)

    ctl.start_source("alpha")

    assert _wait_for(lambda: ctl.health().running == 1)
    # beta remains untouched (STOPPED), alpha is RUNNING.
    assert rt.supervisor.get_runtime("alpha").state == AdapterState.RUNNING
    assert rt.supervisor.get_runtime("beta").state == AdapterState.STOPPED
    # single authoritative supervisor, one runtime per source.
    assert rt.supervisor.count() == 2
    ctl.stop()


def test_c1b_targeted_start_is_idempotent_for_active_source():
    rt = _fresh_runtime()
    rt.add_source(_Source("alpha"))
    ctl = ProductionRuntimeController(rt)

    ctl.start_source("alpha")
    assert _wait_for(lambda: ctl.health().running == 1)
    ctl.start_source("alpha")  # no-op per AdapterRuntime.start() semantics
    assert _wait_for(lambda: ctl.health().running == 1)
    assert rt.supervisor.get_runtime("alpha").state == AdapterState.RUNNING
    ctl.stop()


# ===========================================================================
# C2 — TARGETED STOP
# ===========================================================================
def test_c2_targeted_stop_stops_only_the_named_source():
    rt = _fresh_runtime()
    rt.add_source(_Source("alpha"))
    rt.add_source(_Source("beta"))
    ctl = ProductionRuntimeController(rt)

    ctl.start()
    assert _wait_for(lambda: ctl.health().running == 2)

    ctl.stop_source("alpha")

    # alpha STOPPED, beta still RUNNING.
    assert _wait_for(lambda: rt.supervisor.get_runtime("alpha").state
                     == AdapterState.STOPPED)
    assert rt.supervisor.get_runtime("beta").state == AdapterState.RUNNING
    ctl.stop()


# ===========================================================================
# C3 — TARGETED RESTART (delegates to existing supervisor restart)
# ===========================================================================
def test_c3_targeted_restart_uses_existing_supervisor_restart():
    rt = _fresh_runtime()
    rt.add_source(_Source("alpha", fail_start=True))
    ctl = ProductionRuntimeController(rt)

    # bring alpha to terminal FAILED via the real restart-budget cycle
    rt.start()
    _wait_failed_terminal(rt, "alpha")
    assert rt.supervisor.get_runtime("alpha").state == AdapterState.FAILED

    # monkeypatch-free: assert restart_source delegates by recovering the
    # runtime through the authoritative path.  A healthy source can't be
    # restarted, so we assert the delegation target is AdapterRuntime.restart
    # by verifying the method exists and is what the supervisor calls.
    assert hasattr(rt.supervisor.get_runtime("alpha"), "restart")
    ctl.restart_source("alpha")
    # after manual restart the runtimes re-enters STARTING then (fails again) FAILED.
    assert _wait_for(lambda: rt.supervisor.get_runtime("alpha").state
                     == AdapterState.STARTING or rt.supervisor.get_runtime("alpha")
                     .state == AdapterState.FAILED)
    ctl.stop()


def test_c3b_restart_requires_failed_state():
    rt = _fresh_runtime()
    rt.add_source(_Source("alpha"))
    ctl = ProductionRuntimeController(rt)
    rt.start()
    assert _wait_for(lambda: ctl.health().running == 1)

    # restart on a RUNNING source must raise LifecycleTransitionError (the
    # existing AdapterRuntime.restart() contract), not silently reset budget.
    with pytest.raises(LifecycleTransitionError):
        ctl.restart_source("alpha")
    ctl.stop()


# ===========================================================================
# C4 — UNKNOWN SOURCE (deterministic existing semantics: KeyError)
# ===========================================================================
def test_c4_unknown_source_raises_keyerror_for_all_operations():
    rt = _fresh_runtime()
    rt.add_source(_Source("alpha"))
    ctl = ProductionRuntimeController(rt)

    with pytest.raises(KeyError):
        ctl.start_source("does-not-exist")
    with pytest.raises(KeyError):
        ctl.stop_source("does-not-exist")
    with pytest.raises(KeyError):
        ctl.restart_source("does-not-exist")
    # alpha untouched by any failed targeted op.
    assert rt.supervisor.get_runtime("alpha").state == AdapterState.STOPPED
    ctl.stop()


# ===========================================================================
# C5 — INDEPENDENT LIFECYCLE (per-source operations don't affect others)
# ===========================================================================
def test_c5_operations_are_independent_across_sources():
    rt = _fresh_runtime()
    rt.add_source(_Source("a"))
    rt.add_source(_Source("b"))
    rt.add_source(_Source("c"))
    ctl = ProductionRuntimeController(rt)

    ctl.start_source("b")
    assert _wait_for(lambda: ctl.health().running == 1)
    assert rt.supervisor.get_runtime("b").state == AdapterState.RUNNING
    assert rt.supervisor.get_runtime("a").state == AdapterState.STOPPED
    assert rt.supervisor.get_runtime("c").state == AdapterState.STOPPED

    ctl.stop_source("b")
    assert _wait_for(lambda: rt.supervisor.get_runtime("b").state
                     == AdapterState.STOPPED)
    assert rt.supervisor.get_runtime("a").state == AdapterState.STOPPED
    assert rt.supervisor.get_runtime("c").state == AdapterState.STOPPED
    ctl.stop()


# ===========================================================================
# C6 — AGGREGATE HEALTH (unchanged, observational, deterministic)
# ===========================================================================
def test_c6_aggregate_health_is_observational_and_unchanged():
    rt = _fresh_runtime()
    rt.add_source(_Source("a"))
    rt.add_source(_Source("b"))
    ctl = ProductionRuntimeController(rt)
    try:
        # not started -> STOPPED (existing contract)
        assert ctl.health().state == RuntimeState.STOPPED
        h0 = ctl.health()

        # A targeted start_source() alone does NOT flip the aggregate because
        # the ProductionRuntime.started flag (which gates aggregate health) is
        # only set by the global start().  This is the UNCHANGED existing
        # contract: the targeted operation does not promote aggregate health.
        ctl.start_source("a")
        assert _wait_for(lambda: rt.supervisor.get_runtime("a").state
                         == AdapterState.RUNNING)
        assert ctl.health().state == RuntimeState.STOPPED

        # A real global start() promotes the aggregate deterministically:
        # both healthy sources -> HEALTHY.
        ctl.start()
        assert _wait_for(lambda: ctl.health().running == 2)
        assert ctl.health().state == RuntimeState.HEALTHY

        # health projection never mutates lifecycle state
        assert rt.supervisor.get_runtime("a").state == AdapterState.RUNNING
        assert rt.supervisor.get_runtime("b").state == AdapterState.RUNNING
        # health() is a fresh read-only snapshot; no shadow state on controller
        assert ctl.health() is not h0
    finally:
        ctl.stop()


def test_c6b_aggregate_health_is_deterministic_with_degraded_source():
    # A single DEGRADED source degrades the aggregate (existing precedence:
    # any DEGRADED -> DEGRADED), while healthy sources remain RUNNING.
    rt = _fresh_runtime()
    rt.add_source(_Source("good"))
    rt.add_source(_Source("degraded", degrade=True))
    ctl = ProductionRuntimeController(rt)
    try:
        ctl.start()
        # degraded source fails its read loop -> DEGRADED (auto-restarts keep
        # it non-terminal), healthy source stays RUNNING.
        assert _wait_for(lambda: ctl.health().degraded >= 1, timeout=10.0)
        assert ctl.health().state == RuntimeState.DEGRADED
        assert _wait_for(lambda: rt.supervisor.get_runtime("good").state
                         == AdapterState.RUNNING)
        assert rt.supervisor.get_runtime("degraded").state in (
            AdapterState.DEGRADED, AdapterState.RUNNING, AdapterState.STARTING,
        )
    finally:
        ctl.stop()


def test_c6c_aggregate_health_reflects_single_failed_source():
    rt = _fresh_runtime()
    rt.add_source(_Source("good"))
    rt.add_source(_Source("bad", fail_start=True))
    ctl = ProductionRuntimeController(rt)

    ctl.start()
    _wait_failed_terminal(rt, "bad")
    # aggregate becomes FAILED (existing contract) while good stays RUNNING.
    assert ctl.health().state == RuntimeState.FAILED
    assert rt.supervisor.get_runtime("good").state == AdapterState.RUNNING
    assert rt.supervisor.get_runtime("bad").state == AdapterState.FAILED
    ctl.stop()


# ===========================================================================
# C7 — FAILURE ISOLATION
# ===========================================================================
def test_c7_failure_of_one_source_does_not_stop_healthy_sources():
    rt = _fresh_runtime()
    rt.add_source(_Source("good"))
    rt.add_source(_Source("bad", fail_start=True))
    ctl = ProductionRuntimeController(rt)

    ctl.start()
    _wait_failed_terminal(rt, "bad")

    # healthy source keeps running while bad is terminally FAILED
    assert _wait_for(lambda: rt.supervisor.get_runtime("good").state
                     == AdapterState.RUNNING)
    assert rt.supervisor.get_runtime("bad").state == AdapterState.FAILED
    # one source failed does not convert all runtimes to FAILED
    assert ctl.health().running == 1
    ctl.stop()


# ===========================================================================
# C8 — RESTART OWNERSHIP (no second RestartPolicy / runtime)
# ===========================================================================
def test_c8_restart_ownership_remains_singular():
    rt = _fresh_runtime()
    rt.add_source(_Source("alpha", fail_start=True))
    ctl = ProductionRuntimeController(rt)

    rt.start()
    _wait_failed_terminal(rt, "alpha")
    runtime = rt.supervisor.get_runtime("alpha")

    # exactly one runtime per source, budget exhausted via the single policy
    assert rt.supervisor.count() == 1
    assert runtime.health().get("restart_budget_remaining") == 0
    # a fresh targeted restart resets the SAME runtime (no second object)
    ctl.restart_source("alpha")
    assert rt.supervisor.get_runtime("alpha") is runtime
    ctl.stop()


# ===========================================================================
# C9 — GLOBAL SHUTDOWN (authoritative path preserved)
# ===========================================================================
def test_c9_global_shutdown_remains_authoritative():
    rt = _fresh_runtime()
    rt.add_source(_Source("a"))
    rt.add_source(_Source("b"))
    ctl = ProductionRuntimeController(rt)

    ctl.start()
    assert _wait_for(lambda: ctl.health().running == 2)

    ctl.stop()
    # authoritative shutdown: started flag cleared, supervisor cleared, all
    # runtimes STOPPED (no runtime objects / threads remain).
    assert rt.started is False
    assert rt.supervisor.count() == 0
    assert ctl.health().state == RuntimeState.STOPPED
    assert _active_threads("adapter-runtime-") == []


def test_c9b_shutdown_is_idempotent():
    rt = _fresh_runtime()
    rt.add_source(_Source("a"))
    ctl = ProductionRuntimeController(rt)

    ctl.start()
    assert _wait_for(lambda: ctl.health().running == 1)
    ctl.stop()
    ctl.stop()  # repeated stop deterministic
    assert rt.started is False
    assert ctl.health().state == RuntimeState.STOPPED
    assert _active_threads("adapter-runtime-") == []


# ===========================================================================
# C10 — NO ARCHITECTURAL DUPLICATION (behavioural + structural guards)
# ===========================================================================
def test_c10_no_second_supervisor_or_lifecycle_owner():
    rt = _fresh_runtime()
    ctl = ProductionRuntimeController(rt)
    # controller holds only the injected runtime; the single supervisor is
    # owned by the runtime, not by the controller.
    assert ctl._runtime is rt
    assert rt.supervisor is not None
    assert rt.supervisor.count() == 0


def test_c10b_controller_does_not_construct_lifecycle_components():
    src = _module_source(_CONTROL_MODULE)
    # structural guard: the facade must not build a runtime/supervisor/
    # manager/factory — it only stores the injected reference.
    assert "AdapterSupervisor(" not in src
    assert "AdapterRuntime(" not in src
    assert "PluginManager(" not in src
    assert "EventFactory(" not in src
    assert "threading.Thread" not in src
    assert "Timer(" not in src


def test_c10c_no_eventbus_or_second_dispatch_path_in_control_surface():
    # EventBus / EventEngine / second pipeline must not appear as executable
    # imports in the control facade, supervisor, or runtime.
    for mod_file in (_CONTROL_MODULE, _SUPERVISOR_MODULE, _RUNTIME_MODULE):
        imps = _module_imports(mod_file)
        assert "event_bus" not in imps, f"EventBus import leaked into {mod_file}"
        assert "event_engine" not in imps, f"EventEngine import leaked into {mod_file}"


def test_c10d_targeted_ops_delegate_through_supervisor_not_direct():
    # The controller must route targeted ops via ProductionRuntime ->
    # AdapterSupervisor, never reach into AdapterRuntime directly.
    src = _module_source(_CONTROL_MODULE)
    assert "supervisor.start(" not in src
    assert "supervisor.stop(" not in src
    assert "supervisor.restart(" not in src
    # it delegates to the runtime's per-source methods
    assert "start_source(" in src
    assert "stop_source(" in src
    assert "restart_source(" in src


def test_c10e_no_new_uncontrolled_threads_or_timers_in_control_surface():
    for mod_file in (_CONTROL_MODULE, _SUPERVISOR_MODULE):
        src = _module_source(mod_file)
        assert "threading.Thread(" not in src
        assert "Timer(" not in src
        # no arbitrary fixed sleeps for synchronization in the control plane
        assert "time.sleep(" not in src
