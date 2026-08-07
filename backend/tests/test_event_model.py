"""
Event Layer — Unit Tests.

WO-012-001: Event Layer skeleton.
Covers:
  - Event creation
  - Immutable event (frozen)
  - Event serialization (to_dict / from_dict)
  - Metadata handling
  - Type validation
  - Timestamp generation
"""

from __future__ import annotations

import copy
import threading
from datetime import datetime, timezone

import pytest

from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_status import EventStatus
from app.event.event_types import EventType


# ── Event Creation ──────────────────────────────────────────────


class TestEventCreation:
    def test_create_event_generates_id(self):
        event = Event(
            entity_id="entity-001",
            event_type=EventType.ENTITY_CREATED,
            source="test",
        )
        assert event.event_id is not None
        assert isinstance(event.event_id, str)
        assert len(event.event_id) > 0

    def test_create_event_with_custom_id(self):
        event = Event(
            event_id="custom-id-001",
            entity_id="entity-001",
            event_type=EventType.SIGNAL_RECEIVED,
            source="signal",
        )
        assert event.event_id == "custom-id-001"

    def test_create_event_with_payload(self):
        payload = {"latitude": 50.45, "longitude": 30.52}
        event = Event(
            entity_id="entity-001",
            event_type=EventType.OBSERVATION_CREATED,
            source="observation",
            payload=payload,
        )
        assert event.payload == payload

    def test_create_event_with_metadata(self):
        meta = EventMetadata(
            tags=["urgent", "field"],
            properties={"region": "north"},
            correlation_id="corr-123",
        )
        event = Event(
            entity_id="entity-001",
            event_type=EventType.ENTITY_CREATED,
            source="test",
            metadata=meta,
        )
        assert event.metadata.correlation_id == "corr-123"
        assert event.metadata.tags == ["urgent", "field"]


# ── Immutability ────────────────────────────────────────────────


class TestEventImmutability:
    def test_event_is_frozen(self):
        event = Event(
            entity_id="entity-001",
            event_type=EventType.ENTITY_CREATED,
            source="test",
        )
        with pytest.raises(Exception):
            event.source = "hacked"

    def test_event_payload_cannot_be_reassigned(self):
        event = Event(
            entity_id="entity-001",
            event_type=EventType.ENTITY_CREATED,
            source="test",
        )
        with pytest.raises(Exception):
            event.payload = {"new": "data"}

    def test_event_metadata_is_frozen(self):
        meta = EventMetadata(tags=["a"])
        event = Event(
            entity_id="entity-001",
            event_type=EventType.ENTITY_CREATED,
            source="test",
            metadata=meta,
        )
        with pytest.raises(Exception):
            event.metadata = EventMetadata(tags=["b"])


# ── Serialization ───────────────────────────────────────────────


class TestEventSerialization:
    def test_to_dict(self):
        event = Event(
            entity_id="entity-001",
            event_type=EventType.SIGNAL_RECEIVED,
            source="signal",
            payload={"channel": "primary"},
        )
        data = event.to_dict()
        assert data["event_id"] == event.event_id
        assert data["entity_id"] == "entity-001"
        assert data["event_type"] == "signal.received"
        assert data["source"] == "signal"
        assert data["payload"] == {"channel": "primary"}
        assert data["event_status"] == "registered"
        assert "timestamp" in data
        assert "created_at" in data
        assert "metadata" in data

    def test_from_dict(self):
        data = {
            "event_id": "restore-001",
            "entity_id": "entity-002",
            "event_type": "observation.created",
            "timestamp": "2026-01-01T12:00:00+00:00",
            "source": "test",
            "payload": {"key": "value"},
            "metadata": {
                "tags": ["restored"],
                "properties": {},
                "correlation_id": None,
            },
            "created_at": "2026-01-01T12:00:00+00:00",
        }
        event = Event.from_dict(data)
        assert event.event_id == "restore-001"
        assert event.entity_id == "entity-002"
        assert event.event_type == EventType.OBSERVATION_CREATED
        assert event.source == "test"
        assert event.payload == {"key": "value"}

    def test_roundtrip(self):
        original = Event(
            entity_id="round-001",
            event_type=EventType.SYSTEM_STARTUP,
            source="system",
            metadata=EventMetadata(
                tags=["startup"],
                correlation_id="boot-1",
            ),
        )
        data = original.to_dict()
        restored = Event.from_dict(data)
        assert original.event_id == restored.event_id
        assert original.entity_id == restored.entity_id
        assert original.event_type == restored.event_type
        assert original.source == restored.source
        assert original.metadata.correlation_id == restored.metadata.correlation_id


# ── Metadata ────────────────────────────────────────────────────


class TestMetadataHandling:
    def test_metadata_to_dict(self):
        meta = EventMetadata(
            tags=["alpha", "beta"],
            properties={"level": 3},
            correlation_id="x-99",
        )
        d = meta.to_dict()
        assert d["tags"] == ["alpha", "beta"]
        assert d["properties"]["level"] == 3
        assert d["correlation_id"] == "x-99"

    def test_metadata_from_dict(self):
        d = {
            "tags": ["gamma"],
            "properties": {"x": 1},
            "correlation_id": "c-1",
        }
        meta = EventMetadata.from_dict(d)
        assert meta.tags == ["gamma"]
        assert meta.properties == {"x": 1}
        assert meta.correlation_id == "c-1"

    def test_metadata_empty_defaults(self):
        meta = EventMetadata()
        assert meta.tags == []
        assert meta.properties == {}
        assert meta.correlation_id is None


# ── Type Validation ─────────────────────────────────────────────


class TestTypeValidation:
    def test_invalid_event_type(self):
        with pytest.raises(TypeError, match="event_type"):
            Event(
                entity_id="x",
                event_type="not_an_enum",  # type: ignore
                source="test",
            )

    def test_invalid_payload_type(self):
        with pytest.raises(TypeError, match="payload"):
            Event(
                entity_id="x",
                event_type=EventType.CUSTOM,
                source="test",
                payload="not_a_dict",  # type: ignore
            )

    def test_invalid_source_type(self):
        with pytest.raises(TypeError, match="source"):
            Event(
                entity_id="x",
                event_type=EventType.CUSTOM,
                source=123,  # type: ignore
            )

    def test_metadata_invalid_tags(self):
        with pytest.raises(TypeError, match="tags"):
            EventMetadata(tags="not_a_list")  # type: ignore

    def test_metadata_invalid_properties(self):
        with pytest.raises(TypeError, match="properties"):
            EventMetadata(properties="not_a_dict")  # type: ignore


# ── Timestamp Generation ────────────────────────────────────────


class TestTimestampGeneration:
    def test_timestamp_is_utc(self):
        event = Event(
            entity_id="x",
            event_type=EventType.CUSTOM,
            source="test",
        )
        assert event.timestamp.tzinfo == timezone.utc
        assert event.created_at.tzinfo == timezone.utc

    def test_timestamp_has_time(self):
        before = datetime.now(timezone.utc)
        event = Event(
            entity_id="x",
            event_type=EventType.CUSTOM,
            source="test",
        )
        after = datetime.now(timezone.utc)
        assert before <= event.timestamp <= after
        assert before <= event.created_at <= after


# ── Thread Safety ───────────────────────────────────────────────


class TestThreadSafety:
    def test_lock_exposed(self):
        event = Event(
            entity_id="x",
            event_type=EventType.CUSTOM,
            source="test",
        )
        lock = event.get_lock()
        assert hasattr(lock, "acquire")
        assert hasattr(lock, "release")

    def test_multiple_events_different_locks(self):
        e1 = Event(entity_id="a", event_type=EventType.CUSTOM, source="s")
        e2 = Event(entity_id="b", event_type=EventType.CUSTOM, source="s")
        assert e1.get_lock() is not e2.get_lock()


# ── Status ──────────────────────────────────────────────────────


class TestEventStatus:
    def test_default_status_is_registered(self):
        event = Event(
            entity_id="x",
            event_type=EventType.CUSTOM,
            source="test",
        )
        assert event.event_status == EventStatus.REGISTERED


# ── Equality ────────────────────────────────────────────────────


class TestEventEquality:
    def test_equals_same_id(self):
        e = Event(event_id="same", entity_id="x", event_type=EventType.CUSTOM, source="s")
        assert e.equals(e)

    def test_equals_different_id(self):
        e1 = Event(event_id="a", entity_id="x", event_type=EventType.CUSTOM, source="s")
        e2 = Event(event_id="b", entity_id="x", event_type=EventType.CUSTOM, source="s")
        assert not e1.equals(e2)

    def test_equals_non_event(self):
        e = Event(entity_id="x", event_type=EventType.CUSTOM, source="s")
        assert not e.equals("not an event")  # type: ignore
