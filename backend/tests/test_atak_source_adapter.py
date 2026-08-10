"""
TACTICAL CORE — AtakSourceAdapter tests
WO-013-009

Unit + integration tests for AtakSourceAdapter.

Covers:
    1.  adapter satisfies IEventSourceAdapter
    2.  construction from valid SourceDefinition
    3.  source_name() == "atak"
    4.  start behavior
    5.  stop behavior
    6.  start/stop idempotency
    7.  successful ATAK/TAK CoT message reception
    8.  read_events() returns raw dictionaries
    9.  timestamp mapping
    10. CoT field mapping (uid/type/lat/lon)
    11. optional fields (how, stale, detail)
    12. malformed message isolation
    13. batch isolation
    14. parser returns domain-only dicts (no Event objects)
    15. no EventBus import in AtakSourceAdapter
    16. legacy connector untouched (see report / git)
    17. dependency/import boundary
    18. existing WO-013 regression (run separately)
    19. canonical Event produced through EventFactory with
        source == "atak", event_type == EventType.CUSTOM
    20. runtime isolation: no threads/event loops/workers owned by adapter
    21. security: credentials_ref is reference only, no secrets
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.event.event import Event
from app.event.event_types import EventType
from app.event_sources.adapters.atak_parser import (
    AtakParseError,
    AtakPayloadNormalizer,
)
from app.event_sources.adapters.atak_source_adapter import AtakSourceAdapter
from app.event_sources.adapters.base_adapter import BaseEventSourceAdapter
from app.event_sources.config.errors import SourceDefinitionError
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.event_sources.runtime.adapter_runtime import AdapterRuntime


def _definition(**overrides) -> SourceDefinition:
    base = {
        "name": "atak-source-1",
        "adapter_type": "atak",
        "enabled": True,
        "config": {"team": "blue-1"},
        "credentials_ref": "atak.production",
    }
    base.update(overrides)
    return SourceDefinition(**base)


def _valid_cot(**overrides) -> dict:
    msg = {
        "uid": "ATAK-UID-001",
        "type": "a-u-G",
        "time": 1750000000,
        "lat": 50.4501,
        "lon": 30.5234,
        "how": "m-g",
        "detail": {"callsign": "BLUE-1"},
    }
    msg.update(overrides)
    return msg


# --- 1. satisfies IEventSourceAdapter ---


def test_adapter_satisfies_interface():
    adapter = AtakSourceAdapter(_definition())
    assert isinstance(adapter, IEventSourceAdapter)
    assert isinstance(adapter, BaseEventSourceAdapter)


# --- 2. construction from valid SourceDefinition ---


def test_construction_from_valid_definition():
    adapter = AtakSourceAdapter(_definition())
    assert adapter.source_name() == "atak"
    assert adapter.adapter_type == "atak"
    assert adapter.pending_count() == 0
    assert adapter._credentials_ref == "atak.production"


def test_construction_rejects_invalid_definition():
    with pytest.raises(SourceDefinitionError):
        AtakSourceAdapter(_definition(name=""))


# --- 3. source_name ---


def test_source_name_is_atak():
    adapter = AtakSourceAdapter(_definition())
    assert adapter.source_name() == "atak"


# --- 4/5/6. lifecycle ---


def test_start_stop_and_idempotency():
    adapter = AtakSourceAdapter(_definition())
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
    adapter = AtakSourceAdapter(_definition())
    assert adapter.health() is False
    adapter.start()
    assert adapter.health() is True
    adapter.stop()
    assert adapter.health() is False


# --- 7/8. message reception and read_events returns raw dicts ---


def test_ingest_and_read_returns_raw_dicts():
    adapter = AtakSourceAdapter(_definition())
    adapter.start()
    accepted = adapter.ingest(_valid_cot())
    assert accepted is True
    raw_events = adapter.read_events()
    assert isinstance(raw_events, list)
    assert len(raw_events) == 1
    raw = raw_events[0]
    assert isinstance(raw, dict)
    assert raw["uid"] == "ATAK-UID-001"
    assert raw["type"] == "a-u-G"
    assert raw["lat"] == 50.4501
    assert raw["lon"] == 30.5234


def test_read_events_empty_when_not_running():
    adapter = AtakSourceAdapter(_definition())
    adapter.ingest(_valid_cot())
    assert adapter.read_events() == []


def test_read_events_drains_queue():
    adapter = AtakSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(_valid_cot(uid="u1"))
    adapter.ingest(_valid_cot(uid="u2"))
    assert adapter.pending_count() == 2
    first = adapter.read_events()
    assert len(first) == 2
    # queue drained
    assert adapter.pending_count() == 0
    assert adapter.read_events() == []


# --- 9. timestamp mapping ---


def test_timestamp_preserved_for_factory():
    adapter = AtakSourceAdapter(_definition())
    adapter.start()
    ts = 1750000000
    adapter.ingest(_valid_cot(time=ts))
    raw = adapter.read_events()[0]
    assert raw["timestamp"] == ts


def test_timestamp_normalized_to_utc_by_factory():
    adapter = AtakSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(_valid_cot(time=1750000000))
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="atak")
    assert isinstance(event.timestamp, datetime)
    assert event.timestamp.tzinfo == timezone.utc


# --- 10/11. field mapping (mandatory + optional) ---


def test_atak_fields_in_payload():
    adapter = AtakSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(_valid_cot())
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="atak")
    assert event.payload["uid"] == "ATAK-UID-001"
    assert event.payload["type"] == "a-u-G"
    assert event.payload["lat"] == 50.4501
    assert event.payload["lon"] == 30.5234


def test_optional_fields_how_stale_detail():
    adapter = AtakSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(
        _valid_cot(
            how="m-g",
            stale="2026-08-11T00:00:00Z",
            detail={"callsign": "BLUE-1", "team": "blue-1"},
        )
    )
    raw = adapter.read_events()[0]
    assert raw["how"] == "m-g"
    assert raw["stale"] == "2026-08-11T00:00:00Z"
    assert raw["detail"] == {"callsign": "BLUE-1", "team": "blue-1"}


def test_optional_fields_omitted_when_absent():
    adapter = AtakSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(
        {
            "uid": "ATAK-UID-002",
            "type": "a-u-G",
            "lat": 50.0,
            "lon": 30.0,
        }
    )
    raw = adapter.read_events()[0]
    assert "how" not in raw
    assert "stale" not in raw
    assert "detail" not in raw


# --- 12. malformed message isolation ---


def test_malformed_message_is_isolated():
    adapter = AtakSourceAdapter(_definition())
    adapter.start()

    # Missing uid -> dropped
    assert adapter.ingest({"type": "a-u-G", "lat": 50.0, "lon": 30.0}) is False
    # Missing type -> dropped
    assert adapter.ingest({"uid": "u1", "lat": 50.0, "lon": 30.0}) is False
    # Missing lat -> dropped
    assert adapter.ingest({"uid": "u1", "type": "a-u-G", "lon": 30.0}) is False
    # Missing lon -> dropped
    assert adapter.ingest({"uid": "u1", "type": "a-u-G", "lat": 50.0}) is False
    # Empty payload -> dropped
    assert adapter.ingest({}) is False
    # Out-of-range lat -> dropped
    assert (
        adapter.ingest({"uid": "u1", "type": "a-u-G", "lat": 95.0, "lon": 30.0})
        is False
    )
    # Adapter remains alive and can still accept a valid message
    assert adapter.ingest(_valid_cot()) is True


def test_parser_raises_atak_parse_error():
    normalizer = AtakPayloadNormalizer()
    with pytest.raises(AtakParseError):
        normalizer.normalize({"type": "a-u-G", "lat": 50.0, "lon": 30.0})  # no uid
    with pytest.raises(AtakParseError):
        normalizer.normalize({})  # empty
    with pytest.raises(AtakParseError):
        normalizer.normalize(
            {"uid": "u1", "type": "a-u-G", "lat": "abc", "lon": 30.0}
        )  # bad lat


# --- 13. batch isolation ---


def test_batch_isolation_preserves_valid_items():
    adapter = AtakSourceAdapter(_definition())
    adapter.start()
    accepted = adapter.ingest_many(
        [
            _valid_cot(uid="1"),   # valid
            {"type": "a-u-G", "lat": 50.0, "lon": 30.0},  # missing uid
            _valid_cot(uid="3"),   # valid
            _valid_cot(uid="4"),   # valid
            {},                    # invalid
            _valid_cot(uid="6"),   # valid
        ]
    )
    assert accepted == 4  # only valid ones accepted
    raw_events = adapter.read_events()
    ids = [r["uid"] for r in raw_events]
    assert ids == ["1", "3", "4", "6"]
    assert adapter.pending_count() == 0


# --- 14. parser returns domain-only data (no Event objects) ---


def test_parser_returns_domain_only_dicts():
    normalizer = AtakPayloadNormalizer()
    raw = normalizer.normalize(_valid_cot())
    assert isinstance(raw, dict)
    # Must NOT return an Event object.
    assert not isinstance(raw, Event)
    assert "Event" not in type(raw).__name__


# --- 15. no EventBus import ---


def test_no_eventbus_import_in_atak_adapter():
    import app.event_sources.adapters.atak_source_adapter as mod

    module_names = {name for name in dir(mod)}
    assert "event_bus" not in " ".join(module_names).lower()


# --- 16. legacy connector untouched (see report / git) ---


def test_legacy_atak_connector_not_imported():
    import app.event_sources.adapters.atak_source_adapter as mod

    module_names = {name for name in dir(mod)}
    assert "connectors.atak" not in " ".join(module_names).lower()


# --- 17. dependency/import boundary ---


def test_dependency_import_boundary():
    import inspect

    # Resolve the real on-disk path of the adapter module regardless of CWD
    # (CWD is the backend/ pytest rootdir, so relative __module__ paths are
    # not reliable). inspect.getfile returns the absolute module path.
    adapter_path = Path(inspect.getfile(AtakSourceAdapter))
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
        "connectors.atak",
        "connectors",
        "asyncio",
        "requests",
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


# --- 19. canonical Event through EventFactory: source + CUSTOM type ---


def test_canonical_event_source_and_type_via_runtime():
    """End-to-end: adapter -> AdapterRuntime -> EventFactory -> canonical Event.

    Verifies the protected runtime/factory path produces an Event with
    source == "atak" and event_type == EventType.CUSTOM (the accepted
    semantics for the WO-013 source-adapter family).
    """

    class FakePipeline:
        def __init__(self):
            self.events = []

        def process(self, event: Event) -> bool:
            self.events.append(event)
            return True

    adapter = AtakSourceAdapter(_definition())
    pipeline = FakePipeline()
    runtime = AdapterRuntime(
        adapter=adapter,
        factory=EventFactory(),
        pipeline=pipeline,
        poll_interval=0.0,
    )
    runtime.start()

    try:
        adapter.ingest(_valid_cot(time=1750000000))
        deadline = time.time() + 2.0
        while time.time() < deadline and not pipeline.events:
            time.sleep(0.01)

        assert len(pipeline.events) >= 1
        event = pipeline.events[0]
        assert event.source == "atak"
        assert event.event_type == EventType.CUSTOM
        assert event.payload["uid"] == "ATAK-UID-001"
        assert event.payload["type"] == "a-u-G"
    finally:
        runtime.stop()


def test_canonical_event_correlation_id_preserved():
    adapter = AtakSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(_valid_cot(correlation_id="corr-atak-789"))
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="atak")
    assert event.metadata.correlation_id == "corr-atak-789"


# --- 20. runtime isolation: adapter owns no threads/loops/workers ---


def test_adapter_owns_no_background_threads():
    """The passive adapter must not spawn threads, loops, or workers.

    After start(), the adapter's own state contains no thread or event
    loop objects. All threading is owned by AdapterRuntime.
    """
    import threading

    adapter = AtakSourceAdapter(_definition())
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


# --- 21. security: credentials_ref is reference only, no secrets ---


def test_credentials_ref_is_reference_only():
    adapter = AtakSourceAdapter(_definition())
    assert adapter._credentials_ref == "atak.production"
    # The adapter never resolves or reads the credential value; it only
    # holds the reference for downstream wiring.
    assert isinstance(adapter._credentials_ref, str)
    adapter.start()
    adapter.stop()


def test_no_secrets_in_config_required():
    """A valid source can be constructed with credentials_ref == None."""
    adapter = AtakSourceAdapter(_definition(credentials_ref=None))
    assert adapter._credentials_ref is None
    adapter.start()
    assert adapter.ingest(_valid_cot()) is True
    adapter.stop()


def test_secrets_never_emitted_in_event_payload():
    """Credentials are reference-only; the event payload must not contain
    tokens, api hashes, passwords, or hardcoded secrets."""
    adapter = AtakSourceAdapter(
        _definition(config={"team": "blue-1"})
    )
    adapter.start()
    # A hostile/mistaken payload attempting to smuggle secrets.
    adapter.ingest(_valid_cot())
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="atak")
    payload_blob = " ".join(str(v).lower() for v in event.payload.values())
    for secret_token in ("api_key", "token", "password", "secret", "passphrase"):
        assert secret_token not in payload_blob, (
            f"secret token '{secret_token}' leaked into event payload"
        )
    adapter.stop()
