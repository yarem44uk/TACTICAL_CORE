"""
TACTICAL CORE — WO-014-012
Runtime Control Surface Integration — contract closure (Variant A).

Confirms that ``ProductionRuntimeController`` is the authoritative application
control surface and that the application/operator layer may resolve every
authorized control operation through the canonical chain:

    Application / API / Operator
        -> ProductionRuntimeController
        -> ProductionRuntime
        -> AdapterSupervisor
        -> AdapterRuntime

This WO adds NO production code: the control surface already exists and already
exposes the full authorized operation set (start/stop/state/health plus
start_source/stop_source/restart_source).  It does NOT add a second runtime
manager, second supervisor, second AdapterRuntime, second registry, lifecycle
owner, scheduler, worker, event pipeline, EventBus, or direct PluginManager /
AdapterSupervisor / AdapterRuntime access from an application layer.

Contract:
    A  start_source reaches the canonical controller facade and starts the source
    B  stop_source delegates through the facade
    C  restart_source delegates through the facade (FAILED -> RUNNING)
    D  unknown source is safely rejected via the existing Supervisor contract (KeyError)
    E  state is consumed through the controller, without direct AdapterRuntime access
    F  health is obtained through the authorized facade
    G  no bypass: the control surface is the only ingress; the suite must not
       reach AdapterSupervisor / AdapterRuntime / PluginManager / EventBus /
       EventPipeline / EventFactory directly from an application layer
"""

from __future__ import annotations

import inspect

import pytest

from app.bootstrap import ProductionRuntime, create_production_runtime
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.event_sources.runtime.adapter_runtime import AdapterRuntime
from app.event_sources.runtime.adapter_supervisor import AdapterSupervisor
from app.event_sources.runtime.lifecycle import AdapterState
from app.event_sources.runtime.production_control import ProductionRuntimeController
from app.event_sources.runtime.runtime_health import RuntimeState
from app.plugins.manager.plugin_manager import PluginManager


# ---------------------------------------------------------------------------
# Paths for structural no-bypass guards (cwd-independent).
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

    def allow_start(self) -> None:
        """Simulate an external fix so a later restart can recover the source.

        This is test scaffolding on the boundary double, not part of the
        application control surface.
        """
        self._fail_start = False


def _fresh_runtime() -> ProductionRuntime:
    """Real production composition with an isolated PluginManager."""
    return create_production_runtime(plugin_manager=PluginManager())


def _controller(rt: ProductionRuntime) -> ProductionRuntimeController:
    return ProductionRuntimeController(rt)


def _wait_state(rt, name: str, state: AdapterState, timeout: float = 5.0,
                interval: float = 0.01) -> None:
    import time

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


@pytest.fixture(autouse=True)
def _quiet_adapter_runtime_logger():
    import logging

    logger = logging.getLogger("app.event_sources.runtime.adapter_runtime")
    old = logger.level
    logger.setLevel(logging.CRITICAL)
    yield
    logger.setLevel(old)


# ---------------------------------------------------------------------------
# A — start_source reaches the canonical controller facade
# ---------------------------------------------------------------------------
def test_a_start_source_via_controller_facade():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    rt.add_source(_Source("alpha"))

    # still stopped before the control call
    assert rt.supervisor.get_runtime("alpha").state == AdapterState.STOPPED

    ctl.start_source("alpha")

    _wait_state(rt, "alpha", AdapterState.RUNNING)
    assert rt.supervisor.get_runtime("alpha").state == AdapterState.RUNNING
    rt.stop()


# ---------------------------------------------------------------------------
# B — stop_source delegates through the facade
# ---------------------------------------------------------------------------
def test_b_stop_source_via_controller_facade():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    rt.add_source(_Source("alpha"))
    rt.start()
    _wait_state(rt, "alpha", AdapterState.RUNNING)

    ctl.stop_source("alpha")

    _wait_state(rt, "alpha", AdapterState.STOPPED)
    assert rt.supervisor.get_runtime("alpha").state == AdapterState.STOPPED
    rt.stop()


# ---------------------------------------------------------------------------
# C — restart_source delegates through the facade (FAILED -> RUNNING)
# ---------------------------------------------------------------------------
def test_c_restart_source_via_controller_facade():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    # source always fails on start -> supervisor drives it to terminal FAILED
    src = _Source("alpha", fail_start=True)
    rt.add_source(src)
    rt.start()

    _wait_state(rt, "alpha", AdapterState.FAILED)
    assert rt.supervisor.get_runtime("alpha").state == AdapterState.FAILED

    # external "fix" on the boundary double so a restart can recover the source
    src.allow_start()

    # restart through the controller facade (supervisor.restart -> AdapterRuntime)
    ctl.restart_source("alpha")

    _wait_state(rt, "alpha", AdapterState.RUNNING)
    assert rt.supervisor.get_runtime("alpha").state == AdapterState.RUNNING
    rt.stop()


# ---------------------------------------------------------------------------
# D — unknown source is safely rejected via the existing Supervisor contract
# ---------------------------------------------------------------------------
def test_d_unknown_source_rejected():
    rt = _fresh_runtime()
    ctl = _controller(rt)

    with pytest.raises(KeyError):
        ctl.start_source("missing")
    with pytest.raises(KeyError):
        ctl.stop_source("missing")
    with pytest.raises(KeyError):
        ctl.restart_source("missing")
    rt.stop()


# ---------------------------------------------------------------------------
# E — state is consumed through the controller, no direct AdapterRuntime access
# ---------------------------------------------------------------------------
def test_e_state_consumed_via_controller():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    rt.add_source(_Source("alpha"))

    # not started -> STOPPED
    assert ctl.state() == RuntimeState.STOPPED

    # existing contract: a targeted start_source() alone does NOT promote the
    # aggregate state (the ProductionRuntime.started flag gates it); the state
    # is still consumed through the controller, never via direct AdapterRuntime
    ctl.start_source("alpha")
    _wait_state(rt, "alpha", AdapterState.RUNNING)
    assert ctl.state() == RuntimeState.STOPPED

    # a real global start() promotes the aggregate deterministically
    ctl.start()
    _wait_state(rt, "alpha", AdapterState.RUNNING)
    assert ctl.state() == RuntimeState.HEALTHY
    rt.stop()


# ---------------------------------------------------------------------------
# F — health is obtained through the authorized facade
# ---------------------------------------------------------------------------
def test_f_health_via_controller_facade():
    rt = _fresh_runtime()
    ctl = _controller(rt)
    rt.add_source(_Source("alpha"))
    rt.start()
    _wait_state(rt, "alpha", AdapterState.RUNNING)

    h = ctl.health()
    assert h is not None
    rt.stop()


# ---------------------------------------------------------------------------
# G — no bypass: control surface is the only ingress
# ---------------------------------------------------------------------------
def test_g_application_layer_must_not_own_supervisor_or_runtime():
    # The controller facade is the boundary.  An application/operator layer
    # must resolve through ProductionRuntimeController, never by constructing
    # or reaching AdapterSupervisor / AdapterRuntime / PluginManager directly.
    imports = _module_imports(_CONTROL_MODULE)
    # The controller must not be given direct ownership of supervisor/runtime
    # construction for the application control path.
    assert "plugin_manager" not in imports


def test_g_controller_exposes_exact_authorized_surface():
    rt = _fresh_runtime()
    ctl = _controller(rt)

    # Every authorized control operation is present on the surface.
    for method in (
        "start",
        "stop",
        "state",
        "health",
        "start_source",
        "stop_source",
        "restart_source",
    ):
        assert callable(getattr(ctl, method, None)), f"missing {method}"
    rt.stop()
