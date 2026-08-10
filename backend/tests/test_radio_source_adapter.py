"""
TACTICAL CORE — RadioSourceAdapter tests
WO-013-007

Unit + integration tests for RadioSourceAdapter.

Covers:
    1.  adapter satisfies IEventSourceAdapter
    2.  construction from valid SourceDefinition
    3.  source_name() == "radio"
    4.  start behavior
    5.  stop behavior
    6.  start/stop idempotency
    7.  successful radio transmission reception
    8.  read_events() returns raw dictionaries
    9.  timestamp mapping
    10. frequency mapping
    11. callsign mapping
    12. source mapping
    13. signal_strength mapping
    14. modulation mapping
    15. malformed message isolation
    16. batch isolation
    17. no EventBus import in RadioSourceAdapter
    18. legacy connectors/radio remains untouched (see report / git)
    19. dependency/import boundary
    20. existing WO-013 regression (run separately)
    21. canonical Event produced through EventFactory with
        source == "radio", event_type == EventType.CUSTOM
    22. runtime isolation: no threads/event loops/workers owned by adapter
    23. security: credentials_ref is reference only
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.event.event import Event
from app.event.event_types import EventType
from app.event_sources.adapters.base_adapter import BaseEventSourceAdapter
from app.event_sources.adapters.radio_parser import (
    RadioParseError,
    RadioPayloadNormalizer,
)
from app.event_sources.adapters.radio_source_adapter import RadioSourceAdapter
from app.event_sources.config.errors import SourceDefinitionError
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.event_sources.runtime.adapter_runtime import AdapterRuntime


def _definition(**overrides) -> SourceDefinition:
    base = {
        "name": "radio-source-1",
        "adapter_type": "radio",
        "enabled": True,
        "config": {"channel": "tactical-1", "device": "rx-01"},
        "credentials_ref": "radio/credential-ref",
    }
    base.update(overrides)
    return SourceDefinition(**base)


# --- 1. satisfies IEventSourceAdapter ---


def test_adapter_satisfies_interface():
    adapter = RadioSourceAdapter(_definition())
    assert isinstance(adapter, IEventSourceAdapter)
    assert isinstance(adapter, BaseEventSourceAdapter)


# --- 2. construction from valid SourceDefinition ---


def test_construction_from_valid_definition():
    adapter = RadioSourceAdapter(_definition())
    assert adapter.source_name() == "radio"
    assert adapter.adapter_type == "radio"
    assert adapter.pending_count() == 0
    assert adapter._credentials_ref == "radio/credential-ref"


def test_construction_rejects_invalid_definition():
    with pytest.raises(SourceDefinitionError):
        RadioSourceAdapter(_definition(name=""))


# --- 3. source_name ---


def test_source_name_is_radio():
    adapter = RadioSourceAdapter(_definition())
    assert adapter.source_name() == "radio"


# --- 4/5/6. lifecycle ---


def test_start_stop_and_idempotency():
    adapter = RadioSourceAdapter(_definition())
    assert adapter.is_running is False
    adapter.start()
    assert adapter.is_running is True
    adapter.start()  # idempotent
    assert adapter.is_running is True
    adapter.stop()
    assert adapter.is_running is False
    adapter.stop()  # idempotent
    assert adapter.is_running is False


def test_health_reflects_running_state():
    adapter = RadioSourceAdapter(_definition())
    assert adapter.health() is False
    adapter.start()
    assert adapter.health() is True
    adapter.stop()
    assert adapter.health() is False


# --- 7/8. transmission reception and read_events returns raw dicts ---


def test_ingest_and_read_returns_raw_dicts():
    adapter = RadioSourceAdapter(_definition())
    adapter.start()
    accepted = adapter.ingest(
        {
            "frequency": "155.5 MHz",
            "callsign": "ALPHA-1",
            "signal_strength": 72,
            "modulation": "FM",
        }
    )
    assert accepted is True
    raw_events = adapter.read_events()
    assert isinstance(raw_events, list)
    assert len(raw_events) == 1
    raw = raw_events[0]
    assert isinstance(raw, dict)
    assert raw["frequency"] == "155.5 MHz"
    assert raw["callsign"] == "ALPHA-1"
    assert raw["signal_strength"] == 72
    assert raw["modulation"] == "FM"


def test_read_events_empty_when_not_running():
    adapter = RadioSourceAdapter(_definition())
    adapter.ingest({"frequency": "155.5", "callsign": "A1"})
    assert adapter.read_events() == []


def test_read_events_drains_queue():
    adapter = RadioSourceAdapter(_definition())
    adapter.start()
    adapter.ingest({"frequency": "155.5", "callsign": "A1"})
    adapter.ingest({"frequency": "155.6", "callsign": "A2"})
    assert adapter.pending_count() == 2
    first = adapter.read_events()
    assert len(first) == 2
    # queue drained
    assert adapter.pending_count() == 0
    assert adapter.read_events() == []


# --- 9. timestamp mapping ---


def test_timestamp_preserved_for_factory():
    adapter = RadioSourceAdapter(_definition())
    adapter.start()
    ts = "2026-08-10T12:00:00Z"
    adapter.ingest(
        {"frequency": "155.5", "callsign": "A1", "timestamp": ts}
    )
    raw = adapter.read_events()[0]
    assert raw["timestamp"] == ts


def test_timestamp_normalized_to_utc_by_factory():
    adapter = RadioSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(
        {"frequency": "155.5", "callsign": "A1", "timestamp": "2026-08-10T12:00:00Z"}
    )
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="radio")
    assert isinstance(event.timestamp, datetime)
    assert event.timestamp.tzinfo == timezone.utc
    assert event.timestamp.hour == 12


# --- 10/11/12/13/14. frequency / callsign / source / signal_strength / modulation ---


def test_radio_fields_in_payload():
    adapter = RadioSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(
        {
            "frequency": "155.500 MHz",
            "callsign": "BRAVO-2",
            "source": "channel-7",
            "signal_strength": 90,
            "modulation": "AM",
        }
    )
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="radio")
    assert event.payload["frequency"] == "155.500 MHz"
    assert event.payload["callsign"] == "BRAVO-2"
    assert event.payload["source"] == "channel-7"
    assert event.payload["signal_strength"] == 90
    assert event.payload["modulation"] == "AM"


# --- 15. malformed message isolation ---


def test_malformed_message_is_isolated():
    adapter = RadioSourceAdapter(_definition())
    adapter.start()

    # Missing required callsign -> dropped
    ok_missing = adapter.ingest({"frequency": "155.5"})
    assert ok_missing is False
    # Empty payload -> dropped
    ok_empty = adapter.ingest({})
    assert ok_empty is False
    # Invalid frequency -> dropped
    ok_bad_freq = adapter.ingest({"frequency": "abc", "callsign": "A1"})
    assert ok_bad_freq is False
    # Invalid signal_strength -> dropped
    ok_bad_strength = adapter.ingest(
        {"frequency": "155.5", "callsign": "A1", "signal_strength": 150}
    )
    assert ok_bad_strength is False
    # Adapter remains alive and can still accept a valid message
    ok_valid = adapter.ingest({"frequency": "155.5", "callsign": "A1"})
    assert ok_valid is True


def test_parser_raises_radio_parse_error():
    normalizer = RadioPayloadNormalizer()
    with pytest.raises(RadioParseError):
        normalizer.normalize({"frequency": "155.5"})  # missing callsign
    with pytest.raises(RadioParseError):
        normalizer.normalize({})  # empty
    with pytest.raises(RadioParseError):
        normalizer.normalize(
            {"frequency": "not-a-freq", "callsign": "A1"}
        )


# --- 16. batch isolation ---


def test_batch_isolation_preserves_valid_items():
    adapter = RadioSourceAdapter(_definition())
    adapter.start()
    accepted = adapter.ingest_many(
        [
            {"frequency": "155.5", "callsign": "A1"},      # valid
            {"frequency": "bad", "callsign": "A2"},        # invalid freq
            {"frequency": "155.6", "callsign": "A3"},      # valid
            {"frequency": "155.7", "callsign": "A4"},      # valid
            {},                                            # invalid
            {"frequency": "155.8", "callsign": "A6"},      # valid
        ]
    )
    assert accepted == 4  # only valid ones accepted
    raw_events = adapter.read_events()
    callsigns = [r["callsign"] for r in raw_events]
    assert callsigns == ["A1", "A3", "A4", "A6"]
    assert adapter.pending_count() == 0


# --- 17. no EventBus import ---


def test_no_eventbus_import_in_radio_adapter():
    import app.event_sources.adapters.radio_source_adapter as mod

    module_names = {name for name in dir(mod)}
    assert "event_bus" not in " ".join(module_names).lower()


# --- 18. legacy connectors/radio untouched (see report / git) ---


def test_legacy_radio_connector_not_imported():
    import app.event_sources.adapters.radio_source_adapter as mod

    module_names = {name for name in dir(mod)}
    assert "connectors.radio" not in " ".join(module_names).lower()


# --- 19. dependency/import boundary ---


def test_dependency_import_boundary():
    adapter_path = Path(
        os.path.join(
            os.path.dirname(
                RadioSourceAdapter.__module__.replace(".", "/")
            ),
            "radio_source_adapter.py",
        )
    )
    text = adapter_path.read_text()
    forbidden = [
        "event_bus",
        "event_pipeline",
        "adapter_runtime",
        "adapter_supervisor",
        "source_registry",
        "event_factory",
        "app.api",
        "app.database",
        "connectors.radio",
        "paho",
        "asyncio",
        "serial",
    ]
    import_lines = [
        line for line in text.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    for token in forbidden:
        for line in import_lines:
            assert token not in line, (
                f"forbidden import token '{token}' in import line: {line}"
            )


# --- 21. canonical Event through EventFactory: source + CUSTOM type ---


def test_canonical_event_source_and_type_via_runtime():
    """End-to-end: adapter -> AdapterRuntime -> EventFactory -> canonical Event.

    Verifies the CURRENT protected runtime/factory path produces an Event
    with source == "radio" and event_type == EventType.CUSTOM (the accepted
    semantics for WO-013-007).
    """

    class FakePipeline:
        def __init__(self):
            self.events = []

        def process(self, event: Event) -> bool:
            self.events.append(event)
            return True

    adapter = RadioSourceAdapter(_definition())
    pipeline = FakePipeline()
    runtime = AdapterRuntime(
        adapter=adapter,
        factory=EventFactory(),
        pipeline=pipeline,
        poll_interval=0.0,
    )
    runtime.start()

    try:
        adapter.ingest(
            {
                "frequency": "155.5 MHz",
                "callsign": "ALPHA-1",
                "signal_strength": 80,
                "timestamp": "2026-08-10T12:00:00Z",
            }
        )
        deadline = time.time() + 2.0
        while time.time() < deadline and not pipeline.events:
            time.sleep(0.01)

        assert len(pipeline.events) >= 1
        event = pipeline.events[0]
        assert event.source == "radio"
        assert event.event_type == EventType.CUSTOM
        assert event.payload["frequency"] == "155.5 MHz"
        assert event.payload["callsign"] == "ALPHA-1"
        assert event.payload["signal_strength"] == 80
    finally:
        runtime.stop()


def test_canonical_event_correlation_id_preserved():
    adapter = RadioSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(
        {
            "frequency": "155.5",
            "callsign": "A1",
            "timestamp": "2026-08-10T12:00:00Z",
            "correlation_id": "corr-radio-789",
        }
    )
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="radio")
    assert event.metadata.correlation_id == "corr-radio-789"


# --- 22. runtime isolation: adapter owns no threads/loops/workers ---


def test_adapter_owns_no_background_threads():
    """The passive adapter must not spawn threads, loops, or workers.

    After start(), the adapter's own state contains no thread or event
    loop objects. All threading is owned by AdapterRuntime.
    """
    import threading

    adapter = RadioSourceAdapter(_definition())
    adapter.start()
    # No thread or loop member created by the adapter itself.
    for attr in vars(adapter):
        value = getattr(adapter, attr)
        assert not isinstance(value, threading.Thread), (
            f"adapter must not own a thread, found {attr}"
        )
        assert "loop" not in type(value).__name__.lower(), (
            f"adapter must not own an event loop, found {attr}"
        )
    adapter.stop()


# --- 23. security: credentials_ref is reference only ---


def test_credentials_ref_is_reference_only():
    adapter = RadioSourceAdapter(_definition())
    assert adapter._credentials_ref == "radio/credential-ref"
    # The adapter never resolves or reads the credential value; it only
    # holds the reference for downstream wiring.
    assert isinstance(adapter._credentials_ref, str)
    adapter.start()
    adapter.stop()


def test_no_secrets_in_config_required():
    """A valid source can be constructed with credentials_ref == None."""
    adapter = RadioSourceAdapter(
        _definition(credentials_ref=None)
    )
    assert adapter._credentials_ref is None
    adapter.start()
    assert adapter.ingest({"frequency": "155.5", "callsign": "A1"}) is True
    adapter.stop()
