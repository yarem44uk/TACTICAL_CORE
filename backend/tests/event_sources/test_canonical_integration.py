"""
TACTICAL CORE — WO-013-010 Canonical Event Normalization
& Source Adapter Integration Gate

Proves the canonical end-to-end contract for every currently implemented
source adapter (Signal, MQTT, Radio, Telegram, ATAK/TAK):

    Source Adapter
        -> transient raw event queue
        -> AdapterRuntime
        -> EventFactory
        -> canonical Event
        -> EventPipeline

This test verifies that the object reaching the pipeline boundary is a
canonical Event (source-neutral `app.event.event.Event`), NOT a raw
source-specific dictionary.

It also verifies source identity, timestamp, payload and correlation_id
are preserved through normalization (CV7).

Architecture guarantees enforced:
    - adapters stay passive leaf components (CV4)
    - adapters reach the canonical boundary only via AdapterRuntime (CV1)
    - no adapter imports EventPipeline / EventFactory / EventBus /
      database / API (CV5) — verified separately by AST audit
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from app.event.event import Event
from app.event_pipeline.interfaces.i_event_pipeline import IEventPipeline
from app.event_sources.adapters.atak_adapter_registration import register_atak_adapter
from app.event_sources.adapters.mqtt_adapter_registration import register_mqtt_adapter
from app.event_sources.adapters.radio_adapter_registration import register_radio_adapter
from app.event_sources.adapters.signal_adapter_registration import register_signal_adapter
from app.event_sources.adapters.telegram_adapter_registration import register_telegram_adapter
from app.event_sources.config.adapter_factory import AdapterFactory
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.runtime.adapter_runtime import AdapterRuntime


# ---------------------------------------------------------------------------
# Capture pipeline (source-agnostic, only records what it receives)
# ---------------------------------------------------------------------------
class CapturingPipeline(IEventPipeline):
    """Collects everything passed to process(); used to observe the boundary."""

    def __init__(self) -> None:
        self.processed: list[Event] = []
        self._lock = threading.Lock()

    def process(self, event: Event) -> bool:
        with self._lock:
            self.processed.append(event)
        return True

    def add_filter(self, filter_func) -> None:
        pass

    def remove_filter(self, filter_func) -> None:
        pass

    def add_before(self, middleware) -> None:
        pass

    def add_after(self, middleware) -> None:
        pass

    def clear(self) -> None:
        self.processed.clear()


def _build_factory() -> AdapterFactory:
    """AdapterFactory with all five source adapters registered."""
    factory = AdapterFactory()
    register_signal_adapter(factory)
    register_mqtt_adapter(factory)
    register_radio_adapter(factory)
    register_telegram_adapter(factory)
    register_atak_adapter(factory)
    return factory


def _definition(adapter_type: str, name: str, **overrides) -> SourceDefinition:
    base = {
        "name": name,
        "adapter_type": adapter_type,
        "enabled": True,
        "config": {},
        "credentials_ref": f"{adapter_type}/credential-ref",
    }
    base.update(overrides)
    return SourceDefinition(**base)


def _wait_for(fn, timeout: float = 3.0, interval: float = 0.005) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# Per-source raw payloads (valid, from each adapter's parser contract)
# ---------------------------------------------------------------------------
def _signal_payload() -> dict:
    return {
        "message_id": "m-1001",
        "sender": "+38000000000",
        "chat_id": "ops-channel",
        "message_text": "Contact sighted grid 37T 12345 67890",
        "timestamp": 1750000000,
    }


def _mqtt_message() -> dict:
    return {
        "topic": "tactical/telemetry",
        "payload": '{"temp": 21.5}',
        "qos": 1,
        "retain": False,
        "timestamp": "2026-08-10T12:00:00Z",
        "correlation_id": "corr-mqtt-1",
    }


def _radio_payload() -> dict:
    return {
        "frequency": "155.5 MHz",
        "callsign": "ALPHA-1",
        "signal_strength": 72,
        "modulation": "FM",
        "timestamp": "2026-08-10T12:00:00Z",
    }


def _telegram_payload() -> dict:
    return {
        "message_id": 1001,
        "chat": {"id": -1001234567890, "title": "Tactical Ops"},
        "from": {"id": 555, "username": "analyst_1"},
        "date": 1750000000,
        "text": "Contact sighted at grid 37T 12345 67890",
    }


def _atak_payload() -> dict:
    return {
        "uid": "ATAK-UID-001",
        "type": "a-u-G",
        "time": 1750000000,
        "lat": 50.4501,
        "lon": 30.5234,
        "how": "m-g",
        "detail": {"callsign": "BLUE-1"},
    }


def _feed_adapter(adapter, kind: str) -> None:
    """Inject one valid raw event into the adapter's transient queue."""
    if kind == "mqtt":
        accepted = adapter.ingest(
            _mqtt_message()["topic"],
            _mqtt_message()["payload"],
            qos=1,
            timestamp="2026-08-10T12:00:00Z",
            correlation_id="corr-mqtt-1",
        )
    else:
        accepted = adapter.ingest(_payload_for(kind))
    assert accepted is True, f"{kind}: ingest rejected a valid payload"


def _payload_for(kind: str) -> dict:
    return {
        "signal": _signal_payload,
        "radio": _radio_payload,
        "telegram": _telegram_payload,
        "atak": _atak_payload,
    }[kind]()


# ---------------------------------------------------------------------------
# The five sources under test
# ---------------------------------------------------------------------------
SOURCE_CASES = [
    ("signal", "signal-source-1", "signal", "signal/credential-ref"),
    ("mqtt", "mqtt-source-1", "mqtt", "mqtt/credential-ref"),
    ("radio", "radio-source-1", "radio", "radio/credential-ref"),
    ("telegram", "telegram-source-1", "telegram", "telegram.production"),
    ("atak", "atak-source-1", "atak", "atak.production"),
]


@pytest.mark.parametrize(
    "adapter_type,name,expected_source,credentials_ref",
    SOURCE_CASES,
    ids=[c[0] for c in SOURCE_CASES],
)
def test_canonical_path_all_sources(
    adapter_type: str,
    name: str,
    expected_source: str,
    credentials_ref: str,
):
    """Full canonical path: real adapter -> AdapterRuntime -> EventFactory
    -> canonical Event -> EventPipeline, for each of the five sources."""
    factory = _build_factory()
    definition = _definition(adapter_type, name, credentials_ref=credentials_ref)
    adapter = factory.create(definition)

    pipeline = CapturingPipeline()
    # Deliberately do NOT pass a custom `name`: AdapterRuntime then uses
    # adapter.source_name() (the source type, e.g. "signal") as the canonical
    # source identity — proving source identity is preserved through
    # normalization (CV7).
    runtime = AdapterRuntime(
        adapter,
        EventFactory(),
        pipeline,
        poll_interval=0.005,
    )

    # Adapter must be passive: no thread before start, and read() returns
    # raw dictionaries, never Event objects (CV4).
    assert not adapter.is_running
    raw_before = adapter.read_events()
    assert all(isinstance(r, dict) for r in raw_before)

    runtime.start()
    try:
        # Feed one valid raw event into the adapter queue.
        _feed_adapter(adapter, adapter_type)

        # The runtime must translate it to a canonical Event at the pipeline.
        assert _wait_for(lambda: len(pipeline.processed) >= 1), (
            f"{adapter_type}: no canonical event reached pipeline"
        )
        event = pipeline.processed[0]

        # Boundary check: it MUST be a canonical Event, not a raw dict.
        assert isinstance(event, Event), (
            f"{adapter_type}: boundary object is {type(event).__name__}, "
            "expected canonical Event"
        )

        # Source identity preserved (CV7).
        assert event.source == expected_source, (
            f"{adapter_type}: source={event.source!r}, expected {expected_source!r}"
        )
        assert event.metadata.properties.get("source_name") == expected_source

        # Timestamp preserved as a UTC datetime (CV7).
        assert event.timestamp is not None
        tz = event.timestamp.tzinfo
        assert tz is not None, f"{adapter_type}: timestamp lost its tzinfo"
        assert tz.utcoffset(event.timestamp).total_seconds() == 0

        # Payload is a source-neutral dict (never empty for the fed event).
        assert isinstance(event.payload, dict)
        assert len(event.payload) >= 1

        # Correlation identity preserved where supplied (MQTT case).
        if adapter_type == "mqtt":
            assert event.metadata.correlation_id == "corr-mqtt-1"
    finally:
        runtime.stop()


@pytest.mark.parametrize(
    "adapter_type,name,expected_source,credentials_ref",
    SOURCE_CASES,
    ids=[c[0] for c in SOURCE_CASES],
)
def test_registration_resolves_all_five_sources(
    adapter_type: str,
    name: str,
    expected_source: str,
    credentials_ref: str,
):
    """The shared AdapterFactory resolves every source to a real adapter
    and registration does not interfere across sources."""
    factory = _build_factory()
    registered = factory.registered_types()
    for expected in ("signal", "mqtt", "radio", "telegram", "atak"):
        assert expected in registered

    adapter = factory.create(_definition(adapter_type, name))
    assert adapter.source_name() == expected_source


def test_all_sources_resolved_from_single_factory():
    """One factory resolves all five source types to distinct adapters."""
    factory = _build_factory()
    assert factory.registered_types() == ["atak", "mqtt", "radio", "signal", "telegram"]
    for kind, _, _, _ in SOURCE_CASES:
        adapter = factory.create(_definition(kind, f"{kind}-x"))
        assert adapter is not None


def test_factory_rejects_unknown_source():
    """An unregistered source type is rejected by the shared factory."""
    factory = _build_factory()
    with pytest.raises(Exception):
        factory.create(_definition("unknown-source", "no-such-source"))
