"""
WO-012-006: Event Filter Engine Tests
"""
import sys
import os
from datetime import datetime, timezone
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.environ["PYTHONPATH"] = os.path.join(os.path.dirname(__file__), "..", "..")

import pytest
from app.event.event import Event
from app.event.event_types import EventType
from app.event.event_metadata import EventMetadata
from app.event_filter.event_filter import (
    EventTypeFilter,
    SourceFilter,
    CorrelationIdFilter,
    TimestampRangeFilter,
    MetadataFilter,
    PredicateFilter,
    AndFilter,
    OrFilter,
    NotFilter,
)


@pytest.fixture
def sample_events() -> list[Event]:
    return [
        Event(
            event_id="evt-1",
            event_type=EventType.ENTITY_CREATED,
            source="system",
            metadata=EventMetadata(correlation_id="corr-1"),
        ),
        Event(
            event_id="evt-2",
            event_type=EventType.SIGNAL_RECEIVED,
            source="sensor",
            metadata=EventMetadata(properties={"priority": "high"}),
        ),
        Event(
            event_id="evt-3",
            event_type=EventType.ENTITY_CREATED,
            source="sensor",
            metadata=EventMetadata(correlation_id="corr-2"),
        ),
        Event(
            event_id="evt-4",
            event_type=EventType.SYSTEM_STARTUP,
            source="system",
            metadata=EventMetadata(properties={"priority": "low"}),
        ),
    ]


class TestEventTypeFilter:
    def test_filter_single_type(self, sample_events):
        f = EventTypeFilter([EventType.ENTITY_CREATED])
        result = f.filter(sample_events)
        assert len(result) == 2
        assert all(e.event_type == EventType.ENTITY_CREATED for e in result)

    def test_filter_multiple_types(self, sample_events):
        f = EventTypeFilter([EventType.ENTITY_CREATED, EventType.SIGNAL_RECEIVED])
        result = f.filter(sample_events)
        assert len(result) == 3

    def test_no_match(self, sample_events):
        f = EventTypeFilter([EventType.CUSTOM])
        result = f.filter(sample_events)
        assert len(result) == 0


class TestSourceFilter:
    def test_filter_by_source(self, sample_events):
        f = SourceFilter(["system"])
        result = f.filter(sample_events)
        assert len(result) == 2
        assert all(e.source == "system" for e in result)


class TestCorrelationIdFilter:
    def test_filter_by_correlation_id(self, sample_events):
        f = CorrelationIdFilter("corr-1")
        result = f.filter(sample_events)
        assert len(result) == 1
        assert result[0].event_id == "evt-1"


class TestTimestampRangeFilter:
    def test_filter_by_start(self):
        base = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
        events = [
            Event(event_id="old", timestamp=datetime(2026, 8, 1, 11, 0, 0, tzinfo=timezone.utc)),
            Event(event_id="new", timestamp=datetime(2026, 8, 1, 13, 0, 0, tzinfo=timezone.utc)),
        ]
        f = TimestampRangeFilter(start=base)
        result = f.filter(events)
        assert len(result) == 1
        assert result[0].event_id == "new"


class TestMetadataFilter:
    def test_filter_by_property(self, sample_events):
        f = MetadataFilter("priority", "high")
        result = f.filter(sample_events)
        assert len(result) == 1
        assert result[0].event_id == "evt-2"


class TestPredicateFilter:
    def test_custom_predicate(self, sample_events):
        f = PredicateFilter(lambda e: len(e.event_id) > 4)
        result = f.filter(sample_events)
        assert len(result) == 4


class TestAndFilter:
    def test_and_combination(self, sample_events):
        f1 = EventTypeFilter([EventType.ENTITY_CREATED])
        f2 = SourceFilter(["sensor"])
        f = AndFilter(f1, f2)
        result = f.filter(sample_events)
        assert len(result) == 1
        assert result[0].event_id == "evt-3"


class TestOrFilter:
    def test_or_combination(self, sample_events):
        f1 = EventTypeFilter([EventType.ENTITY_CREATED])
        f2 = SourceFilter(["system"])
        f = OrFilter(f1, f2)
        result = f.filter(sample_events)
        assert len(result) == 3


class TestNotFilter:
    def test_not_filter(self, sample_events):
        f = NotFilter(SourceFilter(["system"]))
        result = f.filter(sample_events)
        assert len(result) == 2
        assert all(e.source == "sensor" for e in result)


class TestEdgeCases:
    def test_empty_event_list(self):
        f = EventTypeFilter([EventType.ENTITY_CREATED])
        assert f.filter([]) == []

    def test_chain_complex(self, sample_events):
        f = AndFilter(
            NotFilter(SourceFilter(["system"])),
            EventTypeFilter([EventType.ENTITY_CREATED]),
        )
        result = f.filter(sample_events)
        assert len(result) == 1
