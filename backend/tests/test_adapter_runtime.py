"""
TACTICAL CORE — AdapterRuntime tests
WO-013-003 (corrected per independent audit B2/B3/B4/M1)

Tests use FAKE adapters. No real MQTT/Signal/Radio/REST connections.

Corrected semantics covered:
    - read_events() failure -> DEGRADED, does NOT consume restart budget,
      does NOT force FAILED, same thread continues (B3)
    - runtime-level failure -> real NEW-thread auto-restart within budget (B4)
    - budget exhaustion -> FAILED, no further auto-restart
    - start() while DEGRADED is a no-op (M1)
    - lifecycle state machine is authoritative, no forced assignment (B2)
    - no duplicate runtime threads (start no-ops keep one thread)
"""

from __future__ import annotations

import threading
import time

import pytest

from app.event.event import Event
from app.event_sources.adapters.base_adapter import BaseEventSourceAdapter
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.runtime.adapter_runtime import AdapterRuntime
from app.event_sources.runtime.lifecycle import (
    AdapterState,
    LifecycleTransitionError,
    can_transition,
    transition,
)
from app.event_sources.runtime.restart_policy import RestartPolicy


class FakePipeline:
    """Captures events passed to process()."""

    def __init__(self) -> None:
        self.processed: list[Event] = []
        self.fail_on = False
        self._lock = threading.Lock()

    def process(self, event: Event) -> bool:
        with self._lock:
            if self.fail_on:
                raise RuntimeError("pipeline boom")
            self.processed.append(event)
        return True


class FakeAdapter(BaseEventSourceAdapter):
    """Deterministic fake adapter for runtime tests.

    fail_start_times: number of consecutive start() failures before success.
    fail_read: if True, read_events() raises.
    """

    def __init__(
        self,
        name: str = "fake",
        events: list[dict] | None = None,
        fail_start_times: int = 0,
    ) -> None:
        super().__init__()
        self._name = name
        self._events = list(events or [])
        self.start_calls = 0
        self.stop_calls = 0
        self.read_calls = 0
        self.fail_start_times = fail_start_times
        self.fail_read = False
        self._lock = threading.Lock()

    def source_name(self) -> str:
        return self._name

    def start(self) -> None:
        with self._lock:
            self.start_calls += 1
            if self.fail_start_times > 0:
                self.fail_start_times -= 1
                raise RuntimeError("start boom")
        super().start()

    def stop(self) -> None:
        self.stop_calls += 1
        super().stop()

    def read_events(self) -> list[dict]:
        with self._lock:
            self.read_calls += 1
            if self.fail_read:
                raise RuntimeError("read boom")
            out, self._events = self._events, []
            return out


def make_runtime(
    adapter=None,
    events=None,
    poll_interval=0.005,
    restart_policy=None,
    fail_start_times=0,
    fail_read=False,
    **kw,
):
    adapter = adapter or FakeAdapter(events=events, fail_start_times=fail_start_times)
    adapter.fail_read = fail_read
    factory = EventFactory()
    pipeline = FakePipeline()
    runtime = AdapterRuntime(
        adapter,
        factory,
        pipeline,
        poll_interval=poll_interval,
        restart_policy=restart_policy,
        **kw,
    )
    return adapter, factory, pipeline, runtime


def wait_for(fn, timeout=2.0, interval=0.005):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


# --- Lifecycle state machine ---

def test_lifecycle_legal_transitions():
    assert can_transition(AdapterState.STOPPED, AdapterState.STARTING)
    assert can_transition(AdapterState.STARTING, AdapterState.RUNNING)
    assert can_transition(AdapterState.RUNNING, AdapterState.DEGRADED)
    assert can_transition(AdapterState.DEGRADED, AdapterState.RUNNING)
    assert can_transition(AdapterState.RUNNING, AdapterState.STOPPING)
    assert can_transition(AdapterState.STOPPING, AdapterState.STOPPED)
    assert can_transition(AdapterState.RUNNING, AdapterState.FAILED)
    assert can_transition(AdapterState.FAILED, AdapterState.STARTING)


def test_lifecycle_forbidden_transitions():
    # FAILED -> RUNNING is forbidden
    with pytest.raises(LifecycleTransitionError):
        transition(AdapterState.FAILED, AdapterState.RUNNING)
    # STOPPED -> RUNNING is forbidden
    with pytest.raises(LifecycleTransitionError):
        transition(AdapterState.STOPPED, AdapterState.RUNNING)
    # DEGRADED -> STARTING is forbidden (no bypass via start)
    with pytest.raises(LifecycleTransitionError):
        transition(AdapterState.DEGRADED, AdapterState.STARTING)


# --- Runtime start ---

def test_runtime_start_reaches_running():
    _, _, _, runtime = make_runtime(events=[{"message": "hi"}])
    assert runtime.state == AdapterState.STOPPED
    runtime.start()
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    runtime.stop()
    assert runtime.state == AdapterState.STOPPED


def test_runtime_start_idempotent():
    _, _, _, runtime = make_runtime()
    runtime.start()
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    first_thread = runtime._thread
    runtime.start()  # second start is a no-op
    assert runtime.state == AdapterState.RUNNING
    assert runtime._thread is first_thread  # no new thread created
    runtime.stop()


# --- Runtime stop ---

def test_runtime_stop_idempotent():
    _, _, _, runtime = make_runtime()
    runtime.start()
    wait_for(lambda: runtime.state == AdapterState.RUNNING)
    runtime.stop()
    runtime.stop()  # second stop is a no-op
    assert runtime.state == AdapterState.STOPPED


def test_runtime_stop_leaves_no_thread():
    _, _, _, runtime = make_runtime()
    runtime.start()
    wait_for(lambda: runtime.state == AdapterState.RUNNING)
    thread = runtime._thread
    runtime.stop()
    assert thread is not None
    assert not thread.is_alive()


def test_stop_from_failed_leaves_stopped():
    # FAILED -> STOPPED via stop() (legal path, no forced assignment)
    _, _, _, runtime = make_runtime(
        fail_start_times=999, restart_policy=RestartPolicy(max_restarts=0)
    )
    runtime.start()
    assert wait_for(lambda: runtime.state == AdapterState.FAILED)
    runtime.stop()
    assert runtime.state == AdapterState.STOPPED


# --- Manual restart ---

def test_manual_restart_only_from_failed():
    _, _, _, runtime = make_runtime()
    with pytest.raises(LifecycleTransitionError):
        runtime.restart()  # STOPPED, not FAILED


def test_manual_restart_from_failed():
    adapter, _, _, runtime = make_runtime(
        fail_start_times=999, restart_policy=RestartPolicy(max_restarts=0)
    )
    runtime.start()
    # start fails immediately -> FAILED (no auto-restart with budget 0)
    assert wait_for(lambda: runtime.state == AdapterState.FAILED)
    # allow restart to succeed now
    adapter.fail_start_times = 0
    runtime.restart()
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    runtime.stop()


def test_start_from_failed_raises():
    # start() while FAILED must not silently bypass lifecycle; use restart()
    _, _, _, runtime = make_runtime(
        fail_start_times=999, restart_policy=RestartPolicy(max_restarts=0)
    )
    runtime.start()
    assert wait_for(lambda: runtime.state == AdapterState.FAILED)
    with pytest.raises(LifecycleTransitionError):
        runtime.start()
    runtime.stop()


# --- B3: read failure semantics ---

def test_read_failure_degrades_without_consuming_budget():
    adapter, _, _, runtime = make_runtime(
        events=[{"message": "ok"}], restart_policy=RestartPolicy(max_restarts=3, restart_delay=0.005)
    )
    runtime.start()
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    first_thread = runtime._thread
    initial_remaining = runtime.health()["restart_budget_remaining"]

    # begin throwing from read_events
    adapter.fail_read = True
    assert wait_for(lambda: runtime.state == AdapterState.DEGRADED)

    # multiple read failures: runtime stays alive, same thread, budget unchanged
    time.sleep(0.05)
    assert runtime.state == AdapterState.DEGRADED
    assert runtime._thread is first_thread
    assert runtime._thread.is_alive()
    assert runtime.health()["restart_budget_remaining"] == initial_remaining
    assert runtime.health()["restarts"] == 0

    # restore successful reads -> recovers to RUNNING without manual restart
    adapter.fail_read = False
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    assert runtime._thread.is_alive()
    runtime.stop()


def test_read_failure_never_forces_failed():
    # even with a very low budget, recoverable read failures do NOT exhaust it
    adapter, _, _, runtime = make_runtime(
        events=[{"message": "ok"}], restart_policy=RestartPolicy(max_restarts=1, restart_delay=0.005)
    )
    runtime.start()
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    adapter.fail_read = True
    time.sleep(0.05)
    # DEGRADED, NOT FAILED, budget NOT consumed
    assert runtime.state == AdapterState.DEGRADED
    assert runtime.health()["restart_budget_remaining"] == 1
    adapter.fail_read = False
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    runtime.stop()


# --- B4: real automatic restart (new thread) ---

def test_runtime_level_failure_performs_real_restart():
    adapter, _, _, runtime = make_runtime(
        fail_start_times=1,
        restart_policy=RestartPolicy(max_restarts=3, restart_delay=0.005),
    )
    runtime.start()
    # first start() fails -> real auto-restart -> new thread -> RUNNING
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    health = runtime.health()
    assert health["restarts"] == 1
    assert health["restart_budget_remaining"] == 2
    runtime.stop()


def test_restart_creates_distinct_new_thread():
    adapter, _, _, runtime = make_runtime(
        fail_start_times=1,
        restart_policy=RestartPolicy(max_restarts=3, restart_delay=0.005),
    )
    old_thread = runtime._thread
    runtime.start()
    # wait until a restart has definitely occurred
    assert wait_for(lambda: runtime.health()["restarts"] >= 1)
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    new_thread = runtime._thread
    assert old_thread is not new_thread
    assert new_thread.is_alive()
    runtime.stop()


def test_restart_budget_exhaustion():
    # adapter.start() always fails; max_restarts=2 -> exactly 2 restarts, then FAILED
    _, _, _, runtime = make_runtime(
        fail_start_times=999,
        restart_policy=RestartPolicy(max_restarts=2, restart_delay=0.005),
    )
    runtime.start()
    assert wait_for(lambda: runtime.state == AdapterState.FAILED)
    health = runtime.health()
    assert health["restarts"] == 2
    assert health["restart_budget_remaining"] == 0
    # wait briefly to confirm no additional thread is spawned after exhaustion
    time.sleep(0.05)
    assert runtime.state == AdapterState.FAILED
    runtime.stop()


# --- M1: DEGRADED start is no-op ---

def test_start_while_degraded_is_noop():
    adapter, _, _, runtime = make_runtime(
        events=[{"message": "ok"}], restart_policy=RestartPolicy(max_restarts=3, restart_delay=0.005)
    )
    runtime.start()
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    first_thread = runtime._thread
    adapter.fail_read = True
    assert wait_for(lambda: runtime.state == AdapterState.DEGRADED)

    runtime.start()  # must be a no-op while DEGRADED
    assert runtime.state == AdapterState.DEGRADED
    assert runtime._thread is first_thread
    assert runtime.health()["restarts"] == 0
    adapter.fail_read = False
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    runtime.stop()


# --- B2: lifecycle bypass impossible ---

def test_set_state_does_not_force_illegal_state():
    _, _, _, runtime = make_runtime()
    # a direct illegal forced assignment is impossible: _set_state raises
    # and leaves the prior state unchanged
    with pytest.raises(LifecycleTransitionError):
        runtime._set_state(AdapterState.RUNNING)  # STOPPED -> RUNNING is illegal
    assert runtime.state == AdapterState.STOPPED


def test_degraded_to_starting_via_start_impossible():
    adapter, _, _, runtime = make_runtime(restart_policy=RestartPolicy(max_restarts=3))
    runtime.start()
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    adapter.fail_read = True
    assert wait_for(lambda: runtime.state == AdapterState.DEGRADED)
    # start() on DEGRADED is a no-op; it does NOT force DEGRADED -> STARTING
    runtime.start()
    assert runtime.state == AdapterState.DEGRADED
    runtime.stop()


# --- F: no duplicate runtime threads ---

def test_no_duplicate_threads_after_repeated_start():
    _, _, _, runtime = make_runtime()
    runtime.start()
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    thread_after_first = runtime._thread
    runtime.start()
    runtime.start()
    assert runtime._thread is thread_after_first
    assert thread_after_first is not None and thread_after_first.is_alive()
    runtime.stop()
    # after stop no runtime thread remains (or is dead)
    assert runtime._thread is None or not runtime._thread.is_alive()


def test_auto_restart_leaves_only_new_thread_alive():
    _, _, _, runtime = make_runtime(
        fail_start_times=1,
        restart_policy=RestartPolicy(max_restarts=3, restart_delay=0.005),
    )
    runtime.start()
    # start() created Thread1 synchronously; restart will replace it
    old_thread = runtime._thread
    assert old_thread is not None
    assert wait_for(lambda: runtime.health()["restarts"] >= 1)
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    new_thread = runtime._thread
    assert old_thread is not new_thread
    assert not old_thread.is_alive()  # old thread terminated
    assert new_thread.is_alive()      # only new thread remains active
    runtime.stop()


# --- Event forwarding ---

def test_runtime_forwards_events_to_pipeline():
    _, _, pipeline, runtime = make_runtime(
        events=[{"message": "a"}, {"message": "b"}]
    )
    runtime.start()
    assert wait_for(lambda: len(pipeline.processed) >= 2)
    runtime.stop()
    assert len(pipeline.processed) >= 2
    for ev in pipeline.processed:
        assert isinstance(ev, Event)
        assert ev.source == "fake"


def test_factory_failure_drops_event_runtime_alive():
    # an event without source data that factory rejects (raw_data None)
    adapter, _, pipeline, runtime = make_runtime()
    runtime.start()
    wait_for(lambda: runtime.state == AdapterState.RUNNING)
    adapter._events = [None]  # type: ignore[assignment]  # not a dict
    time.sleep(0.05)
    assert runtime.state in (AdapterState.RUNNING, AdapterState.DEGRADED)
    runtime.stop()


def test_pipeline_failure_drops_event_runtime_alive():
    adapter, _, pipeline, runtime = make_runtime(events=[{"message": "x"}])
    runtime.start()
    wait_for(lambda: runtime.state == AdapterState.RUNNING)
    pipeline.fail_on = True
    adapter._events = [{"message": "boom"}]
    time.sleep(0.05)
    assert runtime.state in (AdapterState.RUNNING, AdapterState.DEGRADED)
    runtime.stop()


# --- Runtime health ---

def test_runtime_health_snapshot():
    _, _, _, runtime = make_runtime()
    runtime.start()
    wait_for(lambda: runtime.state == AdapterState.RUNNING)
    h = runtime.health()
    assert h["name"] == "fake"
    assert h["healthy"] is True
    assert "state" in h
    assert "restarts" in h
    assert "last_error" in h
    runtime.stop()


# --- Thread cleanup / join ---

def test_runtime_no_leaked_thread_after_many_starts():
    for _ in range(5):
        _, _, _, runtime = make_runtime()
        runtime.start()
        wait_for(lambda: runtime.state == AdapterState.RUNNING)
        runtime.stop()
        assert runtime._thread is None or not runtime._thread.is_alive()
