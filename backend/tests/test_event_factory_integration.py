"""
TACTICAL CORE — Event Factory Integration Tests
WO-013-002

Verify that EventFactory produces canonical Event objects
compatible with the WO-012 Event Processing Layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_sources.factory.event_factory import EventFactory


@pytest.fixture
def factory():
    return EventFactory()


def test_factory_returns_canonical_event(factory: EventFactory):
    result = factory.create_event(
        raw_data={"key": "value"},
        source_name="test_source",
    )
    assert isinstance(result, Event)


def test_factory_preserves_source(factory: EventFactory):
    result = factory.create_event(
        raw_data={"key": "value"},
        source_name="signal_channel_1",
    )
    assert result.source == "signal_channel_1"


def test_factory_preserves_payload(factory: EventFactory):
    payload = {"action": "detected", "target": "entity_42"}
    result = factory.create_event(
        raw_data={"action": "detected", "target": "entity_42"},
        source_name="test_source",
    )
    assert result.payload == payload


def test_factory_preserves_metadata(factory: EventFactory):
    result = factory.create_event(
        raw_data={"key": "value", "correlation_id": "corr-123"},
        source_name="test_source",
        metadata={"extra": "data"},
    )
    assert isinstance(result.metadata, EventMetadata)
    m = result.metadata
    assert m.correlation_id == "corr-123"
    assert m.properties["source_name"] == "test_source"
    assert m.properties["extra"] == "data"


def test_factory_timestamp_datetime_input(factory: EventFactory):
    dt = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    result = factory.create_event(
        raw_data={"timestamp": dt, "msg": "hello"},
        source_name="test",
    )
    assert result.timestamp == dt
    assert "timestamp" not in result.payload
    assert "msg" in result.payload


def test_factory_timestamp_string_input(factory: EventFactory):
    result = factory.create_event(
        raw_data={"timestamp": "2026-03-01T12:00:00+00:00", "msg": "ok"},
        source_name="test",
    )
    assert result.timestamp.year == 2026
    assert result.timestamp.month == 3
    assert result.timestamp.day == 1


def test_factory_timestamp_unix_input(factory: EventFactory):
    epoch = 1700000000
    result = factory.create_event(
        raw_data={"ts": epoch, "msg": "ok"},
        source_name="test",
    )
    expected = datetime.fromtimestamp(epoch, tz=timezone.utc)
    assert result.timestamp == expected


def test_factory_timestamp_fallback(factory: EventFactory):
    before = datetime.now(timezone.utc)
    result = factory.create_event(
        raw_data={"msg": "no_ts"},
        source_name="test",
    )
    after = datetime.now(timezone.utc)
    assert before <= result.timestamp <= after


def test_factory_event_type_explicit(factory: EventFactory):
    result = factory.create_event(
        raw_data={"msg": "hello"},
        source_name="test",
        event_type=EventType.SIGNAL_RECEIVED,
    )
    assert result.event_type == EventType.SIGNAL_RECEIVED


def test_factory_event_type_default(factory: EventFactory):
    result = factory.create_event(
        raw_data={"msg": "hello"},
        source_name="test",
    )
    assert result.event_type == EventType.CUSTOM


def test_factory_invalid_source_empty(factory: EventFactory):
    with pytest.raises(ValueError, match="source_name"):
        factory.create_event(raw_data={"k": "v"}, source_name="")


def test_factory_invalid_source_none(factory: EventFactory):
    with pytest.raises(ValueError, match="source_name"):
        factory.create_event(raw_data={"k": "v"}, source_name="   ")


def test_factory_invalid_raw_data_type(factory: EventFactory):
    with pytest.raises(TypeError, match="raw_data"):
        factory.create_event(raw_data="not a dict", source_name="test")  # type: ignore


def test_factory_protocol_keys_extracted(factory: EventFactory):
    raw: dict[str, Any] = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "time": "ignored",
        "action": "fire",
        "target": "north",
    }
    result = factory.create_event(raw_data=raw, source_name="test")
    # Protocol keys should NOT be in payload
    assert "timestamp" not in result.payload
    assert "time" not in result.payload
    # Data keys SHOULD be in payload
    assert result.payload["action"] == "fire"
    assert result.payload["target"] == "north"
    # Protocol keys should be in metadata properties
    assert "timestamp" in result.metadata.properties


def test_factory_empty_payload(factory: EventFactory):
    result = factory.create_event(
        raw_data={"timestamp": "2026-01-01T00:00:00+00:00"},
        source_name="test",
    )
    assert result.payload == {}


def test_factory_produces_immutable_event(factory: EventFactory):
    result = factory.create_event(
        raw_data={"key": "value"},
        source_name="test",
    )
    # Event is frozen dataclass
    with pytest.raises(Exception):
        result.source = "hacked"  # type: ignore


def test_factory_metadata_correlation_id(factory: EventFactory):
    result = factory.create_event(
        raw_data={"correlation_id": "uuid-abc", "msg": "x"},
        source_name="test",
    )
    assert result.metadata.correlation_id == "uuid-abc"


def test_factory_metadata_tags_empty_by_default(factory: EventFactory):
    result = factory.create_event(
        raw_data={"msg": "x"},
        source_name="test",
    )
    assert result.metadata.tags == []


def test_event_is_compatible_with_pipeline(factory: EventFactory):
    """Verify Event can be serialized/deserialized as required by pipeline."""
    result = factory.create_event(
        raw_data={"action": "test", "value": 42},
        source_name="pipe_test",
        event_type=EventType.CUSTOM,
        metadata={"run": 1},
    )
    d = result.to_dict()
    assert d["source"] == "pipe_test"
    assert d["event_type"] == "custom"
    reconstructed = Event.from_dict(d)
    assert reconstructed.equals(result)
    assert reconstructed.payload == {"action": "test", "value": 42}
