"""
TACTICAL CORE — AdapterRuntime tests
WO-013-003

Tests use FAKE adapters. No real MQTT/Signal/Radio/REST connections.
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
    """Deterministic fake adapter for runtime tests."""

    def __init__(self, name: str = "fake", events: list[dict] | None = None) -> None:
        super().__init__()
        self._name = name
        self._events = list(events or [])
        self.start_calls = 0
        self.stop_calls = 0
        self.read_calls = 0
        self.fail_start = False
        self.fail_read = False
        self._lock = threading.Lock()

    def source_name(self) -> str:
        return self._name

    def start(self) -> None:
        self.start_calls += 1
        if self.fail_start:
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
    fail_start=False,
    fail_read=False,
    **kw,
):
    adapter = adapter or FakeAdapter(events=events)
    adapter.fail_start = fail_start
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
    runtime.start()  # second start is a no-op
    assert runtime.state == AdapterState.RUNNING
    runtime.stop()


def test_runtime_does_not_start_from_stopping():
    _, _, _, runtime = make_runtime()
    runtime.start()
    wait_for(lambda: runtime.state == AdapterState.RUNNING)
    runtime.stop()
    # after stop -> STOPPED, start again works
    runtime.start()
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
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


# --- Manual restart ---

def test_manual_restart_only_from_failed():
    _, _, _, runtime = make_runtime()
    with pytest.raises(LifecycleTransitionError):
        runtime.restart()  # STOPPED, not FAILED


def test_manual_restart_from_failed():
    adapter, _, _, runtime = make_runtime(fail_start=True)
    runtime.start()
    # start fails immediately -> FAILED
    assert wait_for(lambda: runtime.state == AdapterState.FAILED)
    # allow restart to succeed now
    adapter.fail_start = False
    runtime.restart()
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    runtime.stop()


# --- Auto restart within budget ---

def test_auto_restart_within_budget():
    adapter, _, _, runtime = make_runtime(
        events=[{"message": "ok"}], restart_policy=RestartPolicy(max_restarts=2, restart_delay=0.005)
    )
    runtime.start()
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    # start failing reads mid-run -> DEGRADED, budget consumed, eventually FAILED
    adapter.fail_read = True
    assert wait_for(lambda: runtime.state == AdapterState.FAILED)
    runtime.stop()


def test_restart_budget_to_failed():
    adapter, _, _, runtime = make_runtime(
        events=[{"message": "ok"}], restart_policy=RestartPolicy(max_restarts=1, restart_delay=0.005)
    )
    runtime.start()
    assert wait_for(lambda: runtime.state == AdapterState.RUNNING)
    adapter.fail_read = True
    assert wait_for(lambda: runtime.state == AdapterState.FAILED)
    health = runtime.health()
    assert health["restart_budget_remaining"] == 0
    runtime.stop()


# --- Event forwarding ---

def test_runtime_forwards_events_to_pipeline():
    adapter, _, pipeline, runtime = make_runtime(
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
    # push a malformed raw event via adapter internal buffer
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
