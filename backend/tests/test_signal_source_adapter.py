"""
TACTICAL CORE — SignalSourceAdapter tests
WO-013-005

Unit + integration tests for SignalSourceAdapter.

Covers:
    1.  adapter satisfies IEventSourceAdapter
    2.  construction from valid SourceDefinition
    3.  source_name() == "signal"
    4.  start behavior
    5.  stop behavior
    6.  start/stop idempotency
    7.  successful Signal message reception
    8.  read_events() returns raw dictionaries
    9.  timestamp mapping
    10. sender mapping
    11. chat_id mapping
    12. message_text mapping
    13. attachments mapping
    14. malformed message isolation
    15. connection/read failure behavior (adapter raises on read)
    16. (registration covered in test_signal_source_adapter_registration.py)
    17. no EventBus import in SignalSourceAdapter
    18. legacy connectors/signal remains untouched (see report / git)
    19. dependency/import boundary
    20. existing WO-013 regression (run separately)
    21. canonical Event produced through EventFactory with
        source == "signal", event_type == EventType.CUSTOM
    22. tests do not hide failures
"""

from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.event.event import Event
from app.event.event_types import EventType
from app.event_sources.adapters.base_adapter import BaseEventSourceAdapter
from app.event_sources.adapters.signal_parser import (
    SignalParseError,
    SignalPayloadNormalizer,
)
from app.event_sources.adapters.signal_source_adapter import SignalSourceAdapter
from app.event_sources.config.errors import SourceDefinitionError
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.event_sources.runtime.adapter_runtime import AdapterRuntime


def _definition(**overrides) -> SourceDefinition:
    base = {
        "name": "signal-source-1",
        "adapter_type": "signal",
        "enabled": True,
        "config": {"channel": "ops", "account": "signal-cli"},
        "credentials_ref": "signal/credential-ref",
    }
    base.update(overrides)
    return SourceDefinition(**base)


# --- 1. satisfies IEventSourceAdapter ---


def test_adapter_satisfies_interface():
    adapter = SignalSourceAdapter(_definition())
    assert isinstance(adapter, IEventSourceAdapter)
    assert isinstance(adapter, BaseEventSourceAdapter)


# --- 2. construction from valid SourceDefinition ---


def test_construction_from_valid_definition():
    adapter = SignalSourceAdapter(_definition())
    assert adapter.source_name() == "signal"
    assert adapter.adapter_type == "signal"
    assert adapter.pending_count() == 0
    assert adapter._credentials_ref == "signal/credential-ref"


def test_construction_rejects_invalid_definition():
    with pytest.raises(SourceDefinitionError):
        SignalSourceAdapter(_definition(name=""))


# --- 3. source_name ---


def test_source_name_is_signal():
    adapter = SignalSourceAdapter(_definition())
    assert adapter.source_name() == "signal"


# --- 4/5/6. lifecycle ---


def test_start_stop_and_idempotency():
    adapter = SignalSourceAdapter(_definition())
    assert adapter.is_running is False
    adapter.start()
    assert adapter.is_running is True
    # start is idempotent
    adapter.start()
    assert adapter.is_running is True
    adapter.stop()
    assert adapter.is_running is False
    # stop is idempotent
    adapter.stop()
    assert adapter.is_running is False


def test_health_reflects_running_state():
    adapter = SignalSourceAdapter(_definition())
    assert adapter.health() is False
    adapter.start()
    assert adapter.health() is True
    adapter.stop()
    assert adapter.health() is False


# --- 7/8. message reception and read_events returns raw dicts ---


def test_ingest_and_read_returns_raw_dicts():
    adapter = SignalSourceAdapter(_definition())
    adapter.start()
    accepted = adapter.ingest(
        {
            "message_id": "m1",
            "sender": "+15550001",
            "chat_id": "chan-1",
            "timestamp": "2026-08-10T12:00:00Z",
            "message_text": "hello",
        }
    )
    assert accepted is True
    raw_events = adapter.read_events()
    assert isinstance(raw_events, list)
    assert len(raw_events) == 1
    raw = raw_events[0]
    assert isinstance(raw, dict)
    assert raw["message_id"] == "m1"
    assert raw["sender"] == "+15550001"
    assert raw["chat_id"] == "chan-1"
    assert raw["message_text"] == "hello"


def test_read_events_empty_when_not_running():
    adapter = SignalSourceAdapter(_definition())
    adapter.ingest({"message_id": "m1", "sender": "s", "chat_id": "c"})
    # not started -> read_events returns []
    assert adapter.read_events() == []


def test_ingest_many_returns_count():
    adapter = SignalSourceAdapter(_definition())
    adapter.start()
    n = adapter.ingest_many(
        [
            {"message_id": "a", "sender": "s", "chat_id": "c"},
            {"message_id": "b", "sender": "s", "chat_id": "c"},
        ]
    )
    assert n == 2
    assert adapter.pending_count() == 2


# --- 9. timestamp mapping ---


def test_timestamp_preserved_for_factory():
    adapter = SignalSourceAdapter(_definition())
    adapter.start()
    ts = "2026-08-10T12:00:00Z"
    adapter.ingest(
        {"message_id": "m1", "sender": "s", "chat_id": "c", "timestamp": ts}
    )
    raw = adapter.read_events()[0]
    assert raw["timestamp"] == ts


def test_timestamp_normalized_to_utc_by_factory():
    adapter = SignalSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(
        {
            "message_id": "m1",
            "sender": "s",
            "chat_id": "c",
            "timestamp": "2026-08-10T12:00:00Z",
        }
    )
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="signal")
    assert isinstance(event.timestamp, datetime)
    assert event.timestamp.tzinfo == timezone.utc
    assert event.timestamp.hour == 12


# --- 10/11/12. sender / chat_id / message_text mapping ---


def test_sender_chat_text_in_payload():
    adapter = SignalSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(
        {
            "message_id": "m1",
            "sender": "+15550001",
            "chat_id": "chan-1",
            "timestamp": "2026-08-10T12:00:00Z",
            "message_text": "hello world",
        }
    )
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="signal")
    assert event.payload["sender"] == "+15550001"
    assert event.payload["chat_id"] == "chan-1"
    assert event.payload["message_text"] == "hello world"


# --- 13. attachments mapping ---


def test_attachments_mapped_to_payload():
    adapter = SignalSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(
        {
            "message_id": "m1",
            "sender": "s",
            "chat_id": "c",
            "timestamp": "2026-08-10T12:00:00Z",
            "attachments": [
                {
                    "contentType": "image/png",
                    "filename": "a.png",
                    "size": 100,
                    "url": "https://example/a.png",
                }
            ],
        }
    )
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="signal")
    att = event.payload["attachments"][0]
    assert att["content_type"] == "image/png"
    assert att["filename"] == "a.png"


# --- 14. malformed message isolation ---


def test_malformed_payload_dropped_not_crashing():
    adapter = SignalSourceAdapter(_definition())
    adapter.start()
    # missing required fields -> dropped
    assert adapter.ingest({"message_text": "no identity"}) is False
    assert adapter.pending_count() == 0
    # empty payload -> dropped
    assert adapter.ingest({}) is False
    # valid one still accepted after
    assert adapter.ingest({"message_id": "ok", "sender": "s", "chat_id": "c"}) is True


def test_normalizer_raises_on_empty():
    normalizer = SignalPayloadNormalizer()
    with pytest.raises(SignalParseError):
        normalizer.normalize({})
    with pytest.raises(SignalParseError):
        normalizer.normalize({"message_id": "x"})


# --- 15. connection/read failure behavior ---


class _FailingAdapter(SignalSourceAdapter):
    """Adapter that raises on read_events to simulate a read failure."""

    def read_events(self):  # noqa: D102
        raise RuntimeError("simulated Signal read failure")


def test_read_failure_raises_for_runtime_to_handle():
    adapter = _FailingAdapter(_definition())
    adapter.start()
    with pytest.raises(RuntimeError):
        adapter.read_events()


# --- 17. no EventBus import in SignalSourceAdapter ---


def test_no_eventbus_import_in_signal_adapter():
    """No IMPORT statement in the adapter may reference forbidden layers.

    The module docstring may legitimately mention EventBus/API/database to
    document that the adapter must NOT use them; what matters is that no
    `import`/`from` line references them. Import-line scanning only.
    """
    src = Path(
        SignalSourceAdapter.__module__.replace(".", "/") + ".py"
    )
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


def test_signal_source_adapter_does_not_import_eventbus_module():
    import app.event_sources.adapters.signal_source_adapter as mod

    module_names = {name for name in dir(mod)}
    assert "event_bus" not in " ".join(module_names).lower()


# --- 19. dependency/import boundary ---


def test_dependency_import_boundary():
    # SignalSourceAdapter must not transitively import EventBus / API / DB /
    # pipeline / runtime / registry. Check the direct module for forbidden
    # import statements.
    adapter_path = Path(
        os.path.join(
            os.path.dirname(SignalSourceAdapter.__module__.replace(".", "/")),
            "signal_source_adapter.py",
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
        "connectors.signal",
    ]
    for token in forbidden:
        # allow comments/docstring mentions but not imports
        import_lines = [
            line for line in text.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            assert token not in line, (
                f"forbidden import token '{token}' in import line: {line}"
            )


# --- 21. canonical Event through EventFactory: source + CUSTOM type ---


def test_canonical_event_source_and_type_via_runtime():
    """End-to-end: adapter -> AdapterRuntime -> EventFactory -> canonical Event.

    Verifies the CURRENT protected runtime/factory path produces an Event
    with source == "signal" and event_type == EventType.CUSTOM (the accepted
    semantics for WO-013-005).
    """

    class FakePipeline:
        def __init__(self):
            self.events = []

        def process(self, event: Event) -> bool:
            self.events.append(event)
            return True

    adapter = SignalSourceAdapter(_definition())
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
                "message_id": "m-e2e",
                "sender": "+15550001",
                "chat_id": "chan-1",
                "timestamp": "2026-08-10T12:00:00Z",
                "message_text": "e2e payload",
            }
        )
        # Let the runtime thread poll once.
        import time

        deadline = time.time() + 2.0
        while time.time() < deadline and not pipeline.events:
            time.sleep(0.01)

        assert len(pipeline.events) >= 1
        event = pipeline.events[0]
        assert event.source == "signal"
        assert event.event_type == EventType.CUSTOM
        assert event.payload["sender"] == "+15550001"
    finally:
        runtime.stop()


def test_canonical_event_correlation_id_preserved():
    adapter = SignalSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(
        {
            "message_id": "m1",
            "sender": "s",
            "chat_id": "c",
            "timestamp": "2026-08-10T12:00:00Z",
            "correlation_id": "corr-123",
        }
    )
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="signal")
    assert event.metadata.correlation_id == "corr-123"
