"""
TACTICAL CORE — AdapterSupervisor tests
WO-013-003

Tests use FAKE adapters and FAKE pipelines. No real connections.
"""

from __future__ import annotations

import threading
import time

import pytest

from app.event.event import Event
from app.event_sources.adapters.base_adapter import BaseEventSourceAdapter
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.registry.source_registry import SourceRegistry
from app.event_sources.runtime.adapter_runtime import AdapterRuntime
from app.event_sources.runtime.adapter_supervisor import AdapterSupervisor
from app.event_sources.runtime.lifecycle import AdapterState


class RecordingPipeline:
    def __init__(self) -> None:
        self.processed: list[Event] = []
        self._lock = threading.Lock()

    def process(self, event: Event) -> bool:
        with self._lock:
            self.processed.append(event)
        return True

    def add_filter(self, *a, **k):
        pass

    def remove_filter(self, *a, **k):
        pass

    def add_before(self, *a, **k):
        pass

    def add_after(self, *a, **k):
        pass

    def clear(self, *a, **k):
        pass


class FakeAdapter(BaseEventSourceAdapter):
    def __init__(self, name: str, events: list[dict] | None = None) -> None:
        super().__init__()
        self._name = name
        self._events = list(events or [])
        self.fail_start = False
        self.start_calls = 0
        self._lock = threading.Lock()

    def source_name(self) -> str:
        return self._name

    def start(self) -> None:
        self.start_calls += 1
        if self.fail_start:
            raise RuntimeError("start boom")
        super().start()

    def read_events(self) -> list[dict]:
        with self._lock:
            out, self._events = self._events, []
            return out


def make_supervisor(registry=None):
    factory = EventFactory()
    pipeline = RecordingPipeline()
    supervisor = AdapterSupervisor(factory, pipeline, registry=registry)
    return factory, pipeline, supervisor


def wait_for(fn, timeout=2.0, interval=0.005):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


# --- Multiple adapters ---

def test_multiple_adapters_all_start():
    _, pipeline, supervisor = make_supervisor()
    supervisor.add_adapter(FakeAdapter("a", [{"m": 1}]))
    supervisor.add_adapter(FakeAdapter("b", [{"m": 2}]))
    supervisor.add_adapter(FakeAdapter("c", [{"m": 3}]))
    supervisor.start_all()
    assert wait_for(lambda: len(pipeline.processed) >= 3)
    assert supervisor.count() == 3
    supervisor.stop_all()
    assert supervisor.healthy_count() == 0


# --- Adapter A failure does not stop B ---

def test_adapter_a_failure_does_not_stop_b():
    _, pipeline, supervisor = make_supervisor()
    bad = FakeAdapter("bad", [{"m": "x"}])
    bad.fail_start = True
    good = FakeAdapter("good", [{"m": "y"}])
    supervisor.add_adapter(bad)
    supervisor.add_adapter(good)
    supervisor.start_all()
    # good adapter should still process its event
    assert wait_for(lambda: len(pipeline.processed) >= 1)
    # bad runtime should be FAILED, good should be RUNNING
    assert supervisor.get_runtime("bad").state == AdapterState.FAILED
    assert supervisor.get_runtime("good").state == AdapterState.RUNNING
    supervisor.stop_all()


# --- Duplicate registration ---

def test_duplicate_registration_raises():
    _, _, supervisor = make_supervisor()
    supervisor.add_adapter(FakeAdapter("dup"))
    with pytest.raises(ValueError):
        supervisor.add_adapter(FakeAdapter("dup"))


# --- Deregistration ---

def test_deregistration():
    _, _, supervisor = make_supervisor()
    supervisor.add_adapter(FakeAdapter("x"))
    assert supervisor.count() == 1
    supervisor.remove_adapter("x")
    assert supervisor.count() == 0
    with pytest.raises(KeyError):
        supervisor.remove_adapter("x")


# --- Registry integration ---

def test_registry_integration():
    registry = SourceRegistry()
    _, pipeline, supervisor = make_supervisor(registry=registry)
    supervisor.add_adapter(FakeAdapter("r1", [{"m": 1}]))
    supervisor.add_adapter(FakeAdapter("r2", [{"m": 2}]))
    assert registry.count() == 2
    supervisor.start_all()
    assert wait_for(lambda: len(pipeline.processed) >= 2)
    supervisor.stop_all()
    assert registry.count() == 2  # registry is a catalog, stays populated


# --- Supervisor aggregate health ---

def test_supervisor_aggregate_health():
    _, _, supervisor = make_supervisor()
    supervisor.add_adapter(FakeAdapter("a"))
    supervisor.add_adapter(FakeAdapter("b"))
    supervisor.start_all()
    wait_for(lambda: supervisor.healthy_count() == 2)
    health = supervisor.get_health()
    assert len(health) == 2
    names = {h["name"] for h in health}
    assert names == {"a", "b"}
    supervisor.stop_all()


# --- Manual restart via supervisor ---

def test_supervisor_restart_failed_runtime():
    _, pipeline, supervisor = make_supervisor()
    bad = FakeAdapter("bad")
    bad.fail_start = True
    supervisor.add_adapter(bad)
    supervisor.start_all()
    assert wait_for(lambda: supervisor.get_runtime("bad").state == AdapterState.FAILED)
    # allow recovery
    bad.fail_start = False
    supervisor.restart("bad")
    assert wait_for(lambda: supervisor.get_runtime("bad").state == AdapterState.RUNNING)
    supervisor.stop_all()


def test_supervisor_restart_not_failed_raises():
    _, _, supervisor = make_supervisor()
    supervisor.add_adapter(FakeAdapter("a"))
    supervisor.start_all()
    wait_for(lambda: supervisor.get_runtime("a").state == AdapterState.RUNNING)
    with pytest.raises(Exception):
        supervisor.restart("a")  # not FAILED
    supervisor.stop_all()


# --- Shutdown ---

def test_shutdown_clears_all():
    _, pipeline, supervisor = make_supervisor()
    supervisor.add_adapter(FakeAdapter("a", [{"m": 1}]))
    supervisor.add_adapter(FakeAdapter("b", [{"m": 2}]))
    supervisor.start_all()
    wait_for(lambda: len(pipeline.processed) >= 2)
    supervisor.shutdown()
    assert supervisor.count() == 0
    assert supervisor.healthy_count() == 0


# --- Concurrent start/stop ---

def test_concurrent_start_stop():
    _, _, supervisor = make_supervisor()
    for i in range(5):
        supervisor.add_adapter(FakeAdapter(f"c{i}"))
    errors = []

    def do_start():
        try:
            supervisor.start_all()
        except Exception as e:  # pragma: no cover
            errors.append(e)

    def do_stop():
        try:
            supervisor.stop_all()
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=do_start), threading.Thread(target=do_stop)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3)
    assert not errors
    supervisor.shutdown()


# --- Fake adapter -> factory -> pipeline E2E ---

def test_fake_adapter_factory_pipeline_e2e():
    _, pipeline, supervisor = make_supervisor()
    raw = {
        "message": "hello",
        "timestamp": "2026-01-01T00:00:00Z",
        "correlation_id": "cid-1",
    }
    supervisor.add_adapter(FakeAdapter("e2e", [raw]))
    supervisor.start_all()
    assert wait_for(lambda: len(pipeline.processed) >= 1)
    supervisor.stop_all()
    ev = pipeline.processed[0]
    assert isinstance(ev, Event)
    assert ev.source == "e2e"
    assert ev.payload.get("message") == "hello"
    assert ev.metadata.correlation_id == "cid-1"
