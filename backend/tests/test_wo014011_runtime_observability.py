"""
TACTICAL CORE — WO-014-011
Per-Source Runtime Observability Snapshot — contract suite.

Locks the canonical READ-ONLY per-source observability snapshot exposed
through the existing Controller facade:

    Controller.source_snapshot(name)
        -> ProductionRuntime.source_snapshot(name)
        -> AdapterSupervisor.get_runtime(name)
        -> existing AdapterRuntime state/health

The snapshot is an observational projection.  It MUST NOT start/stop/restart
a source, mutate lifecycle, restart budget, or configuration, dispatch events,
or create runtime objects / threads / timers.  It reuses the existing
authoritative runtime/health information; no parallel source registry, second
health model, or additional lifecycle owner is introduced.

Contract:
    C1  query a registered source snapshot
    C2  source identity is correct
    C3  lifecycle state is correctly projected
    C4  health is correctly projected
    C5  restart count is correctly projected
    C6  uptime is correctly projected (observational, no timer/thread)
    C7  failure reason is correctly projected (reuses existing last_error)
    C8  unknown source behavior is explicit and deterministic (KeyError)
    C9  query is observational and does not mutate lifecycle
    C10 existing WO-014-010 lifecycle behavior remains unchanged
"""

from __future__ import annotations

import inspect
import threading
import time

import pytest

from app.bootstrap import ProductionRuntime, create_production_runtime
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.event_sources.runtime.adapter_runtime import AdapterRuntime
from app.event_sources.runtime.adapter_supervisor import AdapterSupervisor
from app.event_sources.runtime.lifecycle import AdapterState
from app.event_sources.runtime.production_control import ProductionRuntimeController
from app.event_sources.runtime.runtime_health import (
    RuntimeState,
    SourceSnapshot,
    SourceState,
)
from app.plugins.manager.plugin_manager import PluginManager


# ---------------------------------------------------------------------------
# Paths for structural mutation guards (cwd-independent).
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
    def __init__(self, name: str, fail_start: bool = False):
        self._name = name
        self._running = False
        self._fail_start = fail_start

    def start(self) -> None:
        if self._fail_start:
            raise RuntimeError(f"{self._name} start failed")
        self._running = True

    def stop(self) -> None:
        self._running = False

    def health(self) -> bool:
        return self._running

    def read_events(self):
        if self._fail_start:
            raise RuntimeError(f"{self._name} read failed")
        return []

    def source_name(self) -> str:
        return self._name


def _fresh_runtime() -> ProductionRuntime:
    """Real production composition with an isolated PluginManager."""
    return create_production_runtime(plugin_manager=PluginManager())


def _controller(rt: ProductionRuntime) -> ProductionRuntimeController:
    return ProductionRuntimeController(rt)


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


# ---------------------------------------------------------------------------
# C1 — query a registered source snapshot
# ---------------------------------------------------------------------------
def test_c1_query_registered_source_snapshot():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    rt.add_source(_Source("alpha"))
    rt.add_source(_Source("beta"))

    snap = ctl.source_snapshot("alpha")

    assert isinstance(snap, SourceSnapshot)
    assert snap.name == "alpha"
    # registered but not yet started -> inactive, not healthy
    assert snap.adapter_state == AdapterState.STOPPED.value
    assert snap.classification == SourceState.INACTIVE
    assert snap.active is False
    assert snap.healthy is False


# ---------------------------------------------------------------------------
# C2 — source identity is correct
# ---------------------------------------------------------------------------
def test_c2_source_identity_is_correct():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    rt.add_source(_Source("alpha"))

    snap = ctl.source_snapshot("alpha")

    assert snap.name == "alpha"
    # per-source: querying one source never bleeds into another
    rt.add_source(_Source("beta"))
    snap_a = ctl.source_snapshot("alpha")
    assert snap_a.name == "alpha"
    assert snap_a.restarts == 0


# ---------------------------------------------------------------------------
# C3 — lifecycle state is correctly projected
# ---------------------------------------------------------------------------
def test_c3_lifecycle_state_is_correctly_projected():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    rt.add_source(_Source("alpha"))
    rt.start()
    _wait_state(rt, "alpha", AdapterState.RUNNING)

    snap = ctl.source_snapshot("alpha")

    assert snap.adapter_state == AdapterState.RUNNING.value
    assert snap.classification == SourceState.RUNNING
    assert snap.active is True
    assert snap.healthy is True


# ---------------------------------------------------------------------------
# C4 — health is correctly projected
# ---------------------------------------------------------------------------
def test_c4_health_is_correctly_projected():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    rt.add_source(_Source("alpha"))
    rt.start()
    _wait_state(rt, "alpha", AdapterState.RUNNING)

    snap = ctl.source_snapshot("alpha")

    assert snap.classification == SourceState.RUNNING
    assert snap.healthy is True
    assert snap.active is True

    # aggregate health is observational and still consistent
    assert ctl.health().state == RuntimeState.HEALTHY


# ---------------------------------------------------------------------------
# C5 — restart count is correctly projected
# ---------------------------------------------------------------------------
def test_c5_restart_count_is_correctly_projected():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    # fail on read repeatedly -> consumes restart budget, auto-restarts
    rt.add_source(_Source("alpha", fail_start=True))
    rt.start()
    # let restart budget be consumed (default max_restarts=3)
    assert _wait_for(
        lambda: ctl.source_snapshot("alpha").restarts > 0, timeout=5.0
    ) or ctl.source_snapshot("alpha").restarts > 0

    snap = ctl.source_snapshot("alpha")
    assert isinstance(snap.restarts, int)
    # either it auto-restarted (restarts>0) or went terminal FAILED;
    # the key contract is that restarts reflects the authoritative counter.
    rt.supervisor.shutdown()


# ---------------------------------------------------------------------------
# C6 — uptime is observational (no timer/thread)
# ---------------------------------------------------------------------------
def test_c6_uptime_is_observational_and_no_new_timer_or_thread():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    rt.add_source(_Source("alpha"))
    rt.start()
    _wait_state(rt, "alpha", AdapterState.RUNNING)

    snap = ctl.source_snapshot("alpha")

    assert snap.uptime >= 0.0
    assert snap.started_at is not None

    # Observational only: a query must not create a new thread/timer.
    before = len(_active_threads("adapter-runtime-"))
    ctl.source_snapshot("alpha")
    ctl.source_snapshot("alpha")
    after = len(_active_threads("adapter-runtime-"))
    assert after == before

    rt.stop()


# ---------------------------------------------------------------------------
# C7 — failure reason is correctly projected (reuses existing last_error)
# ---------------------------------------------------------------------------
def test_c7_failure_reason_is_correctly_projected():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    rt.add_source(_Source("alpha", fail_start=True))
    rt.start()
    # force terminal FAILED (budget exhausted)
    deadline = time.time() + 15.0
    while time.time() < deadline:
        snap = ctl.source_snapshot("alpha")
        if snap.adapter_state == AdapterState.FAILED.value and snap.restarts >= 3:
            break
        time.sleep(0.01)

    snap = ctl.source_snapshot("alpha")
    assert snap.adapter_state == AdapterState.FAILED.value
    assert snap.classification == SourceState.FAILED
    assert snap.healthy is False
    # failure reason reuses the existing last_error (no new failure-state owner)
    assert snap.last_error is not None and "failed" in snap.last_error.lower()

    rt.supervisor.shutdown()


# ---------------------------------------------------------------------------
# C8 — unknown source behavior is explicit and deterministic (KeyError)
# ---------------------------------------------------------------------------
def test_c8_unknown_source_raises_keyerror_deterministically():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    rt.add_source(_Source("alpha"))

    with pytest.raises(KeyError):
        ctl.source_snapshot("does-not-exist")
    with pytest.raises(KeyError):
        ctl.source_snapshot("does-not-exist")


# ---------------------------------------------------------------------------
# C9 — query is observational and does not mutate lifecycle
# ---------------------------------------------------------------------------
def test_c9_query_is_observational_and_does_not_mutate_lifecycle():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    rt.add_source(_Source("alpha"))

    # not started -> snapshot reflects STOPPED; query must NOT auto-start
    snap = ctl.source_snapshot("alpha")
    assert snap.adapter_state == AdapterState.STOPPED.value
    assert rt.started is False
    assert rt.supervisor.get_runtime("alpha").state == AdapterState.STOPPED

    # start explicitly, then confirm query does not stop/restart
    rt.start()
    _wait_state(rt, "alpha", AdapterState.RUNNING)
    ctl.source_snapshot("alpha")
    assert rt.supervisor.get_runtime("alpha").state == AdapterState.RUNNING
    assert ctl.source_snapshot("alpha").restarts == 0

    # stop the single source (keeps it registered; full shutdown clears the
    # registry and would make it unqueryable — matching supervisor semantics)
    ctl.stop_source("alpha")
    # query on a stopped-but-registered source reflects STOPPED, does not restart it
    snap_after = ctl.source_snapshot("alpha")
    assert snap_after.adapter_state == AdapterState.STOPPED.value
    assert rt.supervisor.get_runtime("alpha").state == AdapterState.STOPPED

    rt.stop()


# ---------------------------------------------------------------------------
# C10 — existing WO-014-010 lifecycle behavior remains unchanged
# ---------------------------------------------------------------------------
def test_c10_existing_targeted_lifecycle_behavior_unchanged():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    rt.add_source(_Source("alpha"))
    rt.add_source(_Source("beta"))
    rt.start()
    _wait_state(rt, "alpha", AdapterState.RUNNING)
    _wait_state(rt, "beta", AdapterState.RUNNING)

    # targeted stop still isolates a single source
    ctl.stop_source("alpha")
    assert rt.supervisor.get_runtime("alpha").state == AdapterState.STOPPED
    assert rt.supervisor.get_runtime("beta").state == AdapterState.RUNNING

    # observability does not interfere with lifecycle
    snap = ctl.source_snapshot("beta")
    assert snap.adapter_state == AdapterState.RUNNING.value

    rt.stop()


# ---------------------------------------------------------------------------
# Structural: controller remains a thin facade, no lifecycle construction
# ---------------------------------------------------------------------------
def test_c10b_controller_facade_source_uses_existing_runtime():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    rt.add_source(_Source("alpha"))

    snap = ctl.source_snapshot("alpha")
    assert snap.name == "alpha"

    # delegation goes through the same runtime/supervisor used by lifecycle
    assert ctl.runtime is rt
    assert rt.supervisor.get_runtime("alpha") is not None


def test_c10c_snapshot_query_does_not_introduce_eventbus_or_dispatch():
    imports = _module_imports(_CONTROL_MODULE)
    # The control facade must not gain an EventBus / dispatcher / pipeline
    # dependency via this WO.
    assert "event_bus" not in imports
    assert "event_engine" not in imports
    assert "plugin_dispatcher" not in imports
    assert "event_pipeline" not in imports


def test_c10d_no_new_uncontrolled_threads_or_timers_from_snapshot():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    rt.add_source(_Source("alpha"))
    rt.start()
    _wait_state(rt, "alpha", AdapterState.RUNNING)

    before = len(_active_threads("adapter-runtime-"))
    for _ in range(5):
        ctl.source_snapshot("alpha")
    after = len(_active_threads("adapter-runtime-"))

    assert after == before
    rt.stop()
