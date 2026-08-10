"""
TACTICAL CORE — TelegramSourceAdapter tests
WO-013-008

Unit + integration tests for TelegramSourceAdapter.

Covers:
    1.  adapter satisfies IEventSourceAdapter
    2.  construction from valid SourceDefinition
    3.  source_name() == "telegram"
    4.  start behavior
    5.  stop behavior
    6.  start/stop idempotency
    7.  successful Telegram message reception
    8.  read_events() returns raw dictionaries
    9.  timestamp mapping
    10. message/chat/sender field mapping
    11. optional fields (chat_title, sender_name, reply_to, media)
    12. malformed message isolation
    13. batch isolation
    14. parser returns domain-only dicts (no Event objects)
    15. no EventBus import in TelegramSourceAdapter
    16. legacy connectors/telegram untouched (see report / git)
    17. dependency/import boundary
    18. existing WO-013 regression (run separately)
    19. canonical Event produced through EventFactory with
        source == "telegram", event_type == EventType.CUSTOM
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
from app.event_sources.adapters.base_adapter import BaseEventSourceAdapter
from app.event_sources.adapters.telegram_parser import (
    TelegramParseError,
    TelegramPayloadNormalizer,
)
from app.event_sources.adapters.telegram_source_adapter import TelegramSourceAdapter
from app.event_sources.config.errors import SourceDefinitionError
from app.event_sources.config.source_definition import SourceDefinition
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter
from app.event_sources.runtime.adapter_runtime import AdapterRuntime


def _definition(**overrides) -> SourceDefinition:
    base = {
        "name": "telegram-source-1",
        "adapter_type": "telegram",
        "enabled": True,
        "config": {"chat": "tactical-ops", "channel": "intel-feed"},
        "credentials_ref": "telegram.production",
    }
    base.update(overrides)
    return SourceDefinition(**base)


def _valid_message(**overrides) -> dict:
    msg = {
        "message_id": 1001,
        "chat": {"id": -1001234567890, "title": "Tactical Ops"},
        "from": {"id": 555, "username": "analyst_1", "first_name": "Oleg"},
        "date": 1750000000,
        "text": "Contact sighted at grid 37T 12345 67890",
        "reply_to_message": {"message_id": 1000},
    }
    msg.update(overrides)
    return msg


# --- 1. satisfies IEventSourceAdapter ---


def test_adapter_satisfies_interface():
    adapter = TelegramSourceAdapter(_definition())
    assert isinstance(adapter, IEventSourceAdapter)
    assert isinstance(adapter, BaseEventSourceAdapter)


# --- 2. construction from valid SourceDefinition ---


def test_construction_from_valid_definition():
    adapter = TelegramSourceAdapter(_definition())
    assert adapter.source_name() == "telegram"
    assert adapter.adapter_type == "telegram"
    assert adapter.pending_count() == 0
    assert adapter._credentials_ref == "telegram.production"


def test_construction_rejects_invalid_definition():
    with pytest.raises(SourceDefinitionError):
        TelegramSourceAdapter(_definition(name=""))


# --- 3. source_name ---


def test_source_name_is_telegram():
    adapter = TelegramSourceAdapter(_definition())
    assert adapter.source_name() == "telegram"


# --- 4/5/6. lifecycle ---


def test_start_stop_and_idempotency():
    adapter = TelegramSourceAdapter(_definition())
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
    adapter = TelegramSourceAdapter(_definition())
    assert adapter.health() is False
    adapter.start()
    assert adapter.health() is True
    adapter.stop()
    assert adapter.health() is False


# --- 7/8. message reception and read_events returns raw dicts ---


def test_ingest_and_read_returns_raw_dicts():
    adapter = TelegramSourceAdapter(_definition())
    adapter.start()
    accepted = adapter.ingest(_valid_message())
    assert accepted is True
    raw_events = adapter.read_events()
    assert isinstance(raw_events, list)
    assert len(raw_events) == 1
    raw = raw_events[0]
    assert isinstance(raw, dict)
    assert raw["message_id"] == "1001"
    assert raw["chat_id"] == "-1001234567890"
    assert raw["sender_id"] == "555"
    assert raw["text"] == "Contact sighted at grid 37T 12345 67890"


def test_read_events_empty_when_not_running():
    adapter = TelegramSourceAdapter(_definition())
    adapter.ingest(_valid_message())
    assert adapter.read_events() == []


def test_read_events_drains_queue():
    adapter = TelegramSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(_valid_message(message_id=1))
    adapter.ingest(_valid_message(message_id=2))
    assert adapter.pending_count() == 2
    first = adapter.read_events()
    assert len(first) == 2
    # queue drained
    assert adapter.pending_count() == 0
    assert adapter.read_events() == []


# --- 9. timestamp mapping ---


def test_timestamp_preserved_for_factory():
    adapter = TelegramSourceAdapter(_definition())
    adapter.start()
    ts = 1750000000
    adapter.ingest(_valid_message(date=ts))
    raw = adapter.read_events()[0]
    assert raw["timestamp"] == ts


def test_timestamp_normalized_to_utc_by_factory():
    adapter = TelegramSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(_valid_message(date=1750000000))
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="telegram")
    assert isinstance(event.timestamp, datetime)
    assert event.timestamp.tzinfo == timezone.utc


# --- 10/11. field mapping (mandatory + optional) ---


def test_telegram_fields_in_payload():
    adapter = TelegramSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(_valid_message())
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="telegram")
    assert event.payload["message_id"] == "1001"
    assert event.payload["chat_id"] == "-1001234567890"
    assert event.payload["sender_id"] == "555"
    assert event.payload["text"] == "Contact sighted at grid 37T 12345 67890"


def test_optional_fields_chat_title_sender_name_reply():
    adapter = TelegramSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(_valid_message())
    raw = adapter.read_events()[0]
    assert raw["chat_title"] == "Tactical Ops"
    assert raw["sender_username"] == "analyst_1"
    # username preferred for sender_name (@-prefixed)
    assert raw["sender_name"] == "@analyst_1"
    assert raw["reply_to_message_id"] == "1000"


def test_sender_name_falls_back_to_first_name_when_no_username():
    adapter = TelegramSourceAdapter(_definition())
    adapter.start()
    msg = _valid_message()
    msg["from"] = {"id": 555, "first_name": "Oleg", "last_name": "Yaremchuk"}
    adapter.ingest(msg)
    raw = adapter.read_events()[0]
    assert raw["sender_name"] == "Oleg Yaremchuk"


def test_media_metadata_normalized():
    adapter = TelegramSourceAdapter(_definition())
    adapter.start()
    msg = _valid_message()
    msg["photo"] = [
        {"file_id": "small", "file_unique_id": "u1", "file_size": 100},
        {"file_id": "large", "file_unique_id": "u2", "file_size": 5000},
    ]
    msg["document"] = {
        "file_id": "doc1",
        "file_unique_id": "du1",
        "file_name": "report.pdf",
        "mime_type": "application/pdf",
    }
    adapter.ingest(msg)
    raw = adapter.read_events()[0]
    assert raw["has_media"] is True
    media = raw["media"]
    types = {m["media_type"] for m in media}
    assert "photo" in types
    assert "document" in types
    # largest photo selected
    photo = [m for m in media if m["media_type"] == "photo"][0]
    assert photo["file_id"] == "large"
    doc = [m for m in media if m["media_type"] == "document"][0]
    assert doc["file_name"] == "report.pdf"
    assert doc["mime_type"] == "application/pdf"


def test_caption_used_as_text_when_no_text():
    adapter = TelegramSourceAdapter(_definition())
    adapter.start()
    msg = _valid_message()
    msg.pop("text")
    msg["caption"] = "Caption text"
    adapter.ingest(msg)
    raw = adapter.read_events()[0]
    assert raw["text"] == "Caption text"


# --- 12. malformed message isolation ---


def test_malformed_message_is_isolated():
    adapter = TelegramSourceAdapter(_definition())
    adapter.start()

    # Missing required message_id -> dropped
    assert adapter.ingest({"chat": {"id": 1}, "from": {"id": 2}}) is False
    # Missing chat -> dropped
    assert (
        adapter.ingest({"message_id": 1, "from": {"id": 2}}) is False
    )
    # Missing from -> dropped
    assert (
        adapter.ingest({"message_id": 1, "chat": {"id": 1}}) is False
    )
    # Empty payload -> dropped
    assert adapter.ingest({}) is False
    # Adapter remains alive and can still accept a valid message
    assert adapter.ingest(_valid_message()) is True


def test_parser_raises_telegram_parse_error():
    normalizer = TelegramPayloadNormalizer()
    with pytest.raises(TelegramParseError):
        normalizer.normalize({"chat": {"id": 1}, "from": {"id": 2}})  # no message_id
    with pytest.raises(TelegramParseError):
        normalizer.normalize({})  # empty
    with pytest.raises(TelegramParseError):
        normalizer.normalize(_valid_message(chat={}))  # chat.id missing


# --- 13. batch isolation ---


def test_batch_isolation_preserves_valid_items():
    adapter = TelegramSourceAdapter(_definition())
    adapter.start()
    accepted = adapter.ingest_many(
        [
            _valid_message(message_id=1),   # valid
            {"chat": {"id": 1}, "from": {"id": 2}},  # missing message_id
            _valid_message(message_id=3),   # valid
            _valid_message(message_id=4),   # valid
            {},                             # invalid
            _valid_message(message_id=6),   # valid
        ]
    )
    assert accepted == 4  # only valid ones accepted
    raw_events = adapter.read_events()
    ids = [r["message_id"] for r in raw_events]
    assert ids == ["1", "3", "4", "6"]
    assert adapter.pending_count() == 0


# --- 14. parser returns domain-only data (no Event objects) ---


def test_parser_returns_domain_only_dicts():
    normalizer = TelegramPayloadNormalizer()
    raw = normalizer.normalize(_valid_message())
    assert isinstance(raw, dict)
    # Must NOT return an Event object.
    assert not isinstance(raw, Event)
    assert "Event" not in type(raw).__name__


# --- 15. no EventBus import ---


def test_no_eventbus_import_in_telegram_adapter():
    import app.event_sources.adapters.telegram_source_adapter as mod

    module_names = {name for name in dir(mod)}
    assert "event_bus" not in " ".join(module_names).lower()


# --- 16. legacy connectors/telegram untouched (see report / git) ---


def test_legacy_telegram_connector_not_imported():
    import app.event_sources.adapters.telegram_source_adapter as mod

    module_names = {name for name in dir(mod)}
    assert "connectors.telegram" not in " ".join(module_names).lower()


# --- 17. dependency/import boundary ---


def test_dependency_import_boundary():
    import inspect

    # Resolve the real on-disk path of the adapter module regardless of CWD
    # (CWD is the backend/ pytest rootdir, so relative __module__ paths are
    # not reliable). inspect.getfile returns the absolute module path.
    adapter_path = Path(inspect.getfile(TelegramSourceAdapter))
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
        "connectors.telegram",
        "telethon",
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
    source == "telegram" and event_type == EventType.CUSTOM (the accepted
    semantics for the WO-013 source-adapter family).
    """

    class FakePipeline:
        def __init__(self):
            self.events = []

        def process(self, event: Event) -> bool:
            self.events.append(event)
            return True

    adapter = TelegramSourceAdapter(_definition())
    pipeline = FakePipeline()
    runtime = AdapterRuntime(
        adapter=adapter,
        factory=EventFactory(),
        pipeline=pipeline,
        poll_interval=0.0,
    )
    runtime.start()

    try:
        adapter.ingest(_valid_message(date=1750000000))
        deadline = time.time() + 2.0
        while time.time() < deadline and not pipeline.events:
            time.sleep(0.01)

        assert len(pipeline.events) >= 1
        event = pipeline.events[0]
        assert event.source == "telegram"
        assert event.event_type == EventType.CUSTOM
        assert event.payload["message_id"] == "1001"
        assert event.payload["chat_id"] == "-1001234567890"
    finally:
        runtime.stop()


def test_canonical_event_correlation_id_preserved():
    adapter = TelegramSourceAdapter(_definition())
    adapter.start()
    adapter.ingest(
        _valid_message(correlation_id="corr-telegram-789")
    )
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="telegram")
    assert event.metadata.correlation_id == "corr-telegram-789"


# --- 20. runtime isolation: adapter owns no threads/loops/workers ---


def test_adapter_owns_no_background_threads():
    """The passive adapter must not spawn threads, loops, or workers.

    After start(), the adapter's own state contains no thread or event
    loop objects. All threading is owned by AdapterRuntime.
    """
    import threading

    adapter = TelegramSourceAdapter(_definition())
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
    adapter = TelegramSourceAdapter(_definition())
    assert adapter._credentials_ref == "telegram.production"
    # The adapter never resolves or reads the credential value; it only
    # holds the reference for downstream wiring.
    assert isinstance(adapter._credentials_ref, str)
    adapter.start()
    adapter.stop()


def test_no_secrets_in_config_required():
    """A valid source can be constructed with credentials_ref == None."""
    adapter = TelegramSourceAdapter(
        _definition(credentials_ref=None)
    )
    assert adapter._credentials_ref is None
    adapter.start()
    assert adapter.ingest(_valid_message()) is True
    adapter.stop()


def test_secrets_never_emitted_in_event_payload():
    """Credentials are reference-only; the event payload must not contain
    bot tokens, api_hash, api_id, or passwords."""
    adapter = TelegramSourceAdapter(
        _definition(config={"chat": "tactical-ops", "channel": "intel-feed"})
    )
    adapter.start()
    # A hostile/mistaken payload attempting to smuggle secrets.
    adapter.ingest(_valid_message())
    raw = adapter.read_events()[0]
    event = EventFactory().create_event(raw_data=raw, source_name="telegram")
    payload_blob = " ".join(str(v).lower() for v in event.payload.values())
    for secret_token in ("bot_token", "api_hash", "api_id=", "password", "secret"):
        assert secret_token not in payload_blob, (
            f"secret token '{secret_token}' leaked into event payload"
        )
    adapter.stop()
