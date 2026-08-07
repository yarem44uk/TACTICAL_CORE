"""
TACTICAL CORE — Event Source Framework Tests
WO-013-001

Tests for Source Adapter Framework:
- Adapter lifecycle
- Source Registry
- Event Factory
- Thread safety
"""

import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.event.event import Event
from app.event_sources.adapters.base_adapter import BaseEventSourceAdapter
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.registry.source_registry import SourceRegistry


# --- Test Adapters ---

class MockAdapter(BaseEventSourceAdapter):
    """Test adapter that simulates a real source."""

    def __init__(self, name: str = "mock", fail_on_read: bool = False):
        super().__init__()
        self._name = name
        self._fail_on_read = fail_on_read

    def source_name(self) -> str:
        return self._name

    def read_events(self) -> list[dict]:
        if self._fail_on_read:
            raise RuntimeError("Simulated read failure")
        return [{"content": "test_event", "ts": "2026-01-01T00:00:00Z"}]


class FailingAdapter(BaseEventSourceAdapter):
    """Adapter that fails on start."""

    def source_name(self) -> str:
        return "failing"

    def read_events(self) -> list[dict]:
        return []

    def start(self) -> None:
        super().start()
        raise RuntimeError("Simulated start failure")


# --- Adapter Lifecycle ---

def test_adapter_lifecycle():
    adapter = MockAdapter("test_source")
    assert not adapter.is_running

    adapter.start()
    assert adapter.is_running

    adapter.stop()
    assert not adapter.is_running


def test_adapter_start_idempotent():
    adapter = MockAdapter()
    adapter.start()
    adapter.start()
    assert adapter.is_running


def test_adapter_stop_idempotent():
    adapter = MockAdapter()
    adapter.stop()
    adapter.stop()
    assert not adapter.is_running


def test_adapter_health():
    adapter = MockAdapter()
    assert not adapter.health()
    adapter.start()
    assert adapter.health()


# --- Source Registry ---

def test_adapter_registration():
    registry = SourceRegistry()
    adapter = MockAdapter("reg_test")
    registry.register(adapter)
    assert registry.count() == 1
    assert "reg_test" in registry.list_sources()


def test_adapter_unregister():
    registry = SourceRegistry()
    adapter = MockAdapter("unreg_test")
    registry.register(adapter)
    registry.unregister("unreg_test")
    assert registry.count() == 0


def test_duplicate_registration_raises():
    registry = SourceRegistry()
    registry.register(MockAdapter("dup"))
    with pytest.raises(ValueError):
        registry.register(MockAdapter("dup"))


def test_get_unknown_raises():
    registry = SourceRegistry()
    with pytest.raises(KeyError):
        registry.get("nonexistent")


def test_multiple_adapters():
    registry = SourceRegistry()
    registry.register(MockAdapter("a"))
    registry.register(MockAdapter("b"))
    registry.register(MockAdapter("c"))
    assert registry.count() == 3
    assert registry.list_sources() == ["a", "b", "c"]


def test_failed_adapter_isolation():
    registry = SourceRegistry()
    good = MockAdapter("good")
    failing = FailingAdapter()
    registry.register(good)
    registry.register(failing)

    # start_all should not raise; failure is isolated
    registry.start_all()
    assert good.is_running


# --- Event Factory ---

def test_event_factory_creation():
    factory = EventFactory()
    event = factory.create_event(
        raw_data={"message": "hello", "timestamp": "2026-01-01T00:00:00Z"},
        source_name="test",
    )
    assert isinstance(event, Event)
    assert event.event_id
    assert event.source == "test"
    assert event.payload["message"] == "hello"
    assert event.metadata.properties["source_name"] == "test"


def test_event_factory_numeric_timestamp():
    factory = EventFactory()
    event = factory.create_event(
        raw_data={"data": "x", "ts": 1704067200},
        source_name="numeric",
    )
    assert event.timestamp.year == 2024
    assert event.timestamp.month == 1
    assert event.timestamp.day == 1


def test_event_factory_missing_timestamp():
    factory = EventFactory()
    before = datetime.now(timezone.utc)
    event = factory.create_event(
        raw_data={"content": "no_ts"},
        source_name="no_ts",
    )
    after = datetime.now(timezone.utc)
    assert before <= event.timestamp <= after


def test_event_factory_metadata_merger():
    factory = EventFactory()
    event = factory.create_event(
        raw_data={"msg": "hi"},
        source_name="meta",
        metadata={"priority": "high"},
    )
    assert event.metadata.properties["priority"] == "high"
    assert event.metadata.properties["source_name"] == "meta"


# --- Thread Safety ---

def test_thread_safety():
    registry = SourceRegistry()
    errors = []

    def register_many(prefix: str, count: int) -> None:
        try:
            for i in range(count):
                registry.register(MockAdapter(f"{prefix}_{i}"))
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=register_many, args=("t1", 50))
    t2 = threading.Thread(target=register_many, args=("t2", 50))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    # No unhandled errors (duplicates are ValueError, which is expected)
    # Total should be 100 unique adapters
    assert registry.count() == 100
