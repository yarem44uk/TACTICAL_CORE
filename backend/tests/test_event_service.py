"""Unit tests for EventService (WO-012-005)."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

import pytest

# Import from app. path to match runtime PYTHONPATH=backend convention
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_status import EventStatus
from app.event.event_types import EventType
from app.event_repository.memory_event_repository import MemoryEventRepository
from app.event_service.event_service import EventService
from app.event_service.interfaces.i_event_service import IEventService


@pytest.fixture
def repository():
    return MemoryEventRepository()


@pytest.fixture
def service(repository):
    return EventService(repository)


def _make_event(event_type: EventType = EventType.CUSTOM, source: str = "test") -> Event:
    return Event(
        event_id=str(uuid4()),
        entity_id="entity-1",
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        source=source,
        payload={"key": "value"},
        metadata=EventMetadata(tags=["test"]),
    )


# ===========================================================================
# save_event
# ===========================================================================

def test_save_event(service, repository):
    event = _make_event()
    service.save_event(event)
    assert repository.exists(event.event_id)
    assert repository.get(event.event_id).equals(event)


def test_save_events(service, repository):
    events = [_make_event(source="src1"), _make_event(source="src2"), _make_event(source="src3")]
    service.save_events(events)
    for e in events:
        assert repository.exists(e.event_id)


# ===========================================================================
# get_event / get_events
# ===========================================================================

def test_get_event_found(service, repository):
    event = _make_event()
    service.save_event(event)
    result = service.get_event(event.event_id)
    assert result is not None
    assert result.equals(event)


def test_get_event_not_found(service):
    assert service.get_event("nonexistent") is None


def test_get_events_empty(service):
    assert service.get_events() == []


def test_get_events_after_save(service):
    e1 = _make_event(source="a")
    e2 = _make_event(source="b")
    service.save_events([e1, e2])
    all_events = service.get_events()
    assert len(all_events) == 2


# ===========================================================================
# archive_event
# ===========================================================================

def test_archive_event(service, repository):
    event = _make_event()
    service.save_event(event)
    result = service.archive_event(event.event_id)
    assert result is True
    # Archived event still exists with same ID
    archived = repository.get(event.event_id)
    assert archived is not None
    assert "archived" in archived.metadata.tags
    assert archived.metadata.properties["original_event_id"] == event.event_id


def test_archive_nonexistent(service):
    assert service.archive_event("nonexistent") is False


# ===========================================================================
# exists
# ===========================================================================

def test_exists_true(service, repository):
    event = _make_event()
    service.save_event(event)
    assert service.exists(event.event_id)


def test_exists_false(service):
    assert service.exists("nonexistent") is False


# ===========================================================================
# statistics
# ===========================================================================

def test_statistics_empty(service):
    stats = service.statistics()
    assert stats["total_events"] == 0
    assert stats["by_type"] == {}
    assert stats["by_source"] == {}


def test_statistics_after_save(service):
    service.save_event(_make_event(event_type=EventType.ENTITY_CREATED, source="src_a"))
    service.save_event(_make_event(event_type=EventType.ENTITY_CREATED, source="src_a"))
    service.save_event(_make_event(event_type=EventType.CUSTOM, source="src_b"))
    stats = service.statistics()
    assert stats["total_events"] == 3
    assert stats["by_type"]["entity.created"] == 2
    assert stats["by_type"]["custom"] == 1
    assert stats["by_source"]["src_a"] == 2
    assert stats["by_source"]["src_b"] == 1


# ===========================================================================
# export / import
# ===========================================================================

def test_export_empty(service):
    assert service.export() == []


def test_export(service):
    events = [_make_event(), _make_event()]
    service.save_events(events)
    exported = service.export()
    assert len(exported) == 2
    assert isinstance(exported[0], dict)
    assert "event_id" in exported[0]
    assert "event_type" in exported[0]


def test_import(service, repository):
    original = _make_event()
    data = [original.to_dict()]
    count = service.import_events(data)
    assert count == 1
    imported = repository.get(original.event_id)
    assert imported is not None
    assert imported.equals(original)


def test_import_invalid_data(service):
    count = service.import_events([{"bad": "data"}])
    assert count == 0


def test_export_then_import_roundtrip(service, repository):
    events = [
        _make_event(event_type=EventType.ENTITY_CREATED, source="alpha"),
        _make_event(event_type=EventType.SIGNAL_RECEIVED, source="beta"),
    ]
    service.save_events(events)
    exported = service.export()
    assert len(exported) == 2

    fresh_repo = MemoryEventRepository()
    fresh_service = EventService(fresh_repo)
    imported_count = fresh_service.import_events(exported)
    assert imported_count == 2
    assert fresh_service.statistics()["total_events"] == 2


# ===========================================================================
# IEventService implementation check
# ===========================================================================

def test_implements_interface(service):
    assert isinstance(service, IEventService)


# ===========================================================================
# thread safety
# ===========================================================================

def test_thread_safety_concurrent_save(service):
    events: List[Event] = []
    barrier = threading.Barrier(10)

    def worker():
        barrier.wait()
        e = _make_event(source=f"thread-{threading.current_thread().name}")
        service.save_event(e)
        events.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    stats = service.statistics()
    assert stats["total_events"] == 10


def test_thread_safety_concurrent_read_write(service):
    e = _make_event()
    service.save_event(e)
    errors: List[Exception] = []
    stop = threading.Event()

    def writer():
        while not stop.is_set():
            service.save_event(_make_event(source="concurrent"))

    def reader():
        while not stop.is_set():
            try:
                service.get_events()
                service.statistics()
                service.export()
            except Exception as exc:
                errors.append(exc)

    t1 = threading.Thread(target=writer)
    t2 = threading.Thread(target=reader)
    t1.start()
    t2.start()
    time.sleep(0.3)
    stop.set()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert len(errors) == 0, f"Thread errors: {errors}"
