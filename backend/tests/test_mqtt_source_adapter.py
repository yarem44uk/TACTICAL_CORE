"""
TACTICAL CORE — MQTTSourceAdapter tests
WO-013-006

Unit + integration tests for MQTTSourceAdapter.

Covers:
    1.  adapter satisfies IEventSourceAdapter
    2.  construction from valid SourceDefinition
    3.  source_name() == "mqtt"
    4.  start behavior
    5.  stop behavior
    6.  start/stop idempotency
    7.  successful MQTT message reception
    8.  read_events() returns raw dictionaries
    9.  timestamp mapping
    10. topic mapping
    11. payload mapping
    12. qos mapping
    13. retain mapping
    14. client_id mapping
    15. malformed message isolation
    16. batch isolation
    17. no EventBus import in MQTTSourceAdapter
    18. legacy connectors/mqtt remains untouched (see report / git)
    19. dependency/import boundary
    20. existing WO-013 regression (run separately)
    21. canonical Event produced through EventFactory with
        source == "mqtt", event_type == EventType.CUSTOM
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
from app.event_sources.adapters.mqtt_parser import (
    MQTTParseError,
    MQTTPayloadNormalizer,
)
from app.event_sources.adapters.mqtt_source_adapter import MQTTSourceAdapter
from app.event_sources.config.errors import SourceDefinitionError
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.event_sources.runtime.adapter_runtime import AdapterRuntime


def _definition(**overrides) -> SourceDefinition:
    base = {
        "name": "mqtt-source-1",
        "adapter_type": "mqtt",
        "enabled": True,
        "config": {"topics": ["tactical/telemetry"], "client_id": "tc-core"},
        "credentials_ref": "mqtt/credential-ref",
    }
    base.update(overrides)
    return SourceDefinition(**base)


# --- 1. satisfies IEventSourceAdapter ---


def test_adapter_satisfies_interface():
    adapter = MQTTSourceAdapter(_definition())
    assert isinstance(adapter, IEventSourceAdapter)
    assert isinstance(adapter, BaseEventSourceAdapter)


# --- 2. construction from valid SourceDefinition ---


def test_construction_from_valid_definition():
    adapter = MQTTSourceAdapter(_definition())
    assert adapter.source_name() == "mqtt"
    assert adapter.adapter_type == "mqtt"
    assert adapter.pending_count() == 0
    assert adapter._credentials_ref == "mqtt/credential-ref"


def test_construction_rejects_invalid_definition():
    with pytest.raises(SourceDefinitionError):
        MQTTSourceAdapter(_definition(name=""))


# --- 3. source_name ---


def test_source_name_is_mqtt():
    adapter = MQTTSourceAdapter(_definition())
    assert adapter.source_name() == "mqtt"


# --- 4/5/6. lifecycle ---


def test_start_stop_and_idempotency():
    adapter = MQTTSourceAdapter(_definition())
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
    adapter = MQTTSourceAdapter(_definition())
    assert adapter.health() is False
    adapter.start()
    assert adapter.health() is True
    adapter.stop()
    assert adapter.health() is False


# --- 7/8. message reception and read_events returns raw dicts ---


def test_ingest_and_read_returns_raw_dicts():
    adapter = MQTTSourceAdapter(_definition())
    adapter.start()
    accepted = adapter.ingest("tactical/telemetry", '{"temp": 21.5}', qos=1)
    assert accepted is True
    raw_events = adapter.read_events()
    assert isinstance(raw_events, list)
    assert len(raw_events) == 1
    raw = raw_events[0]
    assert isinstance(raw, dict)
    assert raw["topic"] == "tactical/telemetry"
    assert raw["payload"] == '{"temp": 21.5}'
    assert raw["qos"] == 1


def test_read_events_empty_when_not_running():
    adapter = MQTTSourceAdapter(_definition())
    adapter.ingest("tactical/telemetry", "x")
    assert adapter.read_events() == []


def test_read_events_drains_queue():
    adapter = MQTTSourceAdapter(_definition())
    adapter.start()
    adapter.ingest("tactical/a", "1")
    adapter.ingest("tactical/b", "2")
    assert adapter.pending_count() == 2
    first = adapter.read_events()
    assert len(first) == 2
    # queue drained
    assert adapter.pending_count() == 0
    assert adapter.read_events() == []


# --- 9. timestamp mapping ---


def test_timestamp_preserved_for_factory():
    adapter = MQTTSourceAdapter(_definition())
    adapter.start()
    ts = "2026-08-10T12:00:00Z"
    adapter.ingest("tactical/telemetry", "x", timestamp=ts)
    raw = adapter.read_events()[0]
    assert raw["timestamp"] == ts


def test_timestamp_normalized_to_utc_by_factory():
    adapter = MQTTSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(
        "tactical/telemetry", "x", timestamp="2026-08-10T12:00:00Z"
    )
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="mqtt")
    assert isinstance(event.timestamp, datetime)
    assert event.timestamp.tzinfo == timezone.utc
    assert event.timestamp.hour == 12


# --- 10/11/12/13/14. topic / payload / qos / retain / client_id mapping ---


def test_mqtt_fields_in_payload():
    adapter = MQTTSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(
        "tactical/telemetry",
        '{"temp": 21.5}',
        qos=2,
        retain=True,
        client_id="probe-1",
        timestamp="2026-08-10T12:00:00Z",
    )
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="mqtt")
    assert event.payload["topic"] == "tactical/telemetry"
    assert event.payload["payload"] == '{"temp": 21.5}'
    assert event.payload["qos"] == 2
    assert event.payload["retain"] is True
    assert event.payload["client_id"] == "probe-1"


def test_default_qos_and_retain():
    adapter = MQTTSourceAdapter(_definition())
    adapter.start()
    adapter.ingest("tactical/telemetry", "x")
    raw = adapter.read_events()[0]
    assert raw["qos"] == 0
    assert raw["retain"] is False


def test_bytes_payload_decoded():
    adapter = MQTTSourceAdapter(_definition())
    adapter.start()
    assert adapter.ingest("tactical/telemetry", b"hello") is True
    raw = adapter.read_events()[0]
    assert raw["payload"] == "hello"


# --- 15. malformed message isolation ---


def test_malformed_message_dropped_not_crashing():
    adapter = MQTTSourceAdapter(_definition())
    adapter.start()
    # missing topic -> dropped
    assert adapter.ingest("", "x") is False
    # missing payload -> dropped
    assert adapter.ingest("tactical/a", None) is False
    # invalid qos -> dropped
    assert adapter.ingest("tactical/a", "x", qos=5) is False
    # non-utf8 bytes -> dropped
    assert adapter.ingest("tactical/a", b"\xff\xfe\x00") is False
    assert adapter.pending_count() == 0
    # valid message still accepted after failures
    assert adapter.ingest("tactical/a", "ok") is True


def test_normalizer_raises_on_invalid():
    normalizer = MQTTPayloadNormalizer()
    with pytest.raises(MQTTParseError):
        normalizer.normalize({})
    with pytest.raises(MQTTParseError):
        normalizer.normalize({"topic": "tactical/a"})  # no payload
    with pytest.raises(MQTTParseError):
        normalizer.normalize(
            {"topic": "tactical/a", "payload": "x", "qos": 9}
        )


# --- 16. batch isolation ---


def test_ingest_many_batch_isolation():
    adapter = MQTTSourceAdapter(_definition())
    adapter.start()
    n = adapter.ingest_many(
        [
            {"topic": "tactical/a", "payload": "1"},
            {"topic": "tactical/b", "payload": "2"},
            {"topic": "", "payload": "bad"},  # dropped
            {"payload": "no-topic"},  # dropped
            "not-a-dict",  # dropped
        ]
    )
    assert n == 2
    assert adapter.pending_count() == 2


# --- 17. no EventBus import in MQTTSourceAdapter ---


def test_no_eventbus_import_in_mqtt_adapter():
    """No IMPORT statement in the adapter may reference forbidden layers."""
    src = Path(MQTTSourceAdapter.__module__.replace(".", "/") + ".py")
    text = src.read_text()
    import_lines = [
        line for line in text.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    forbidden = ("event_bus", "EventBus", "app.api", "app.database")
    for token in forbidden:
        for line in import_lines:
            assert token not in line, (
                f"forbidden import token '{token}' in import line: {line}"
            )


def test_mqtt_source_adapter_does_not_import_eventbus_module():
    import app.event_sources.adapters.mqtt_source_adapter as mod

    module_names = {name for name in dir(mod)}
    assert "event_bus" not in " ".join(module_names).lower()


# --- 19. dependency/import boundary ---


def test_dependency_import_boundary():
    adapter_path = Path(
        os.path.join(
            os.path.dirname(
                MQTTSourceAdapter.__module__.replace(".", "/")
            ),
            "mqtt_source_adapter.py",
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
        "connectors.mqtt",
        "paho",
        "asyncio",
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
    with source == "mqtt" and event_type == EventType.CUSTOM (the accepted
    semantics for WO-013-006).
    """

    class FakePipeline:
        def __init__(self):
            self.events = []

        def process(self, event: Event) -> bool:
            self.events.append(event)
            return True

    adapter = MQTTSourceAdapter(_definition())
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
            "tactical/telemetry",
            '{"temp": 21.5}',
            qos=1,
            timestamp="2026-08-10T12:00:00Z",
        )
        deadline = time.time() + 2.0
        while time.time() < deadline and not pipeline.events:
            time.sleep(0.01)

        assert len(pipeline.events) >= 1
        event = pipeline.events[0]
        assert event.source == "mqtt"
        assert event.event_type == EventType.CUSTOM
        assert event.payload["topic"] == "tactical/telemetry"
        assert event.payload["payload"] == '{"temp": 21.5}'
    finally:
        runtime.stop()


def test_canonical_event_correlation_id_preserved():
    adapter = MQTTSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(
        "tactical/telemetry",
        "x",
        timestamp="2026-08-10T12:00:00Z",
        correlation_id="corr-456",
    )
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="mqtt")
    assert event.metadata.correlation_id == "corr-456"


# --- 22. runtime isolation: adapter owns no threads/loops/workers ---


def test_adapter_owns_no_background_threads():
    """The passive adapter must not spawn threads, loops, or workers.

    After start(), the adapter's own state contains no thread or event
    loop objects. All threading is owned by AdapterRuntime.
    """
    import threading

    adapter = MQTTSourceAdapter(_definition())
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
    adapter = MQTTSourceAdapter(_definition())
    assert adapter._credentials_ref == "mqtt/credential-ref"
    # The adapter never resolves or reads the credential value; it only
    # holds the reference for downstream wiring.
    assert isinstance(adapter._credentials_ref, str)
    adapter.start()
    adapter.stop()


def test_no_secrets_in_config_required():
    """A valid source can be constructed with credentials_ref == None."""
    adapter = MQTTSourceAdapter(
        _definition(credentials_ref=None)
    )
    assert adapter._credentials_ref is None
    adapter.start()
    assert adapter.ingest("tactical/a", "x") is True
    adapter.stop()
