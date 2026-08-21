"""WO-025 — Durable event identity & end-to-end idempotency.

Proves that a duplicate delivery of the same logical source message maps to
the same canonical ``event_id`` (via the WO-025 EventIdentityResolver wired
into EventFactory), and that the durable repository + UNIQUE(event_id)
deduplicates it end-to-end to exactly one row.

Uses the real canonical components — EventFactory, EventIdentityResolver,
AdapterRuntime, EventPipeline, SQLAlchemyEventRepository — against a real
file-backed SQLite database.  No mocked repositories or fake migration
engines.
"""

from __future__ import annotations

import os
import tempfile
import threading
from datetime import datetime, timezone

import pytest

from app.composition import create_event_runtime
from app.database.session import (
    configure_session_manager,
    get_session_manager,
)
from app.event.event import Event
from app.event_repository.durable.durable_event_model import DurableCanonicalEvent
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.event_sources.factory.event_factory import EventFactory
from app.event_sources.identity.event_identity import (
    EventIdentityResolver,
    resolve_event_identity,
)

from sqlalchemy import text


def _make_signal_raw(message_id: str, chat_id: str = "chat-1") -> dict:
    return {
        "message_id": message_id,
        "chat_id": chat_id,
        "sender": "alice",
        "message_text": "hello",
    }


def _make_mqtt_raw(topic: str, payload: dict) -> dict:
    return {"topic": topic, "payload": payload}


def _make_radio_raw(frequency: str, callsign: str) -> dict:
    return {"frequency": frequency, "callsign": callsign}


# ---------------------------------------------------------------------------
# 1. Same logical source message delivered twice -> same event_id
# ---------------------------------------------------------------------------


def test_same_logical_message_same_event_id():
    resolver = EventIdentityResolver()
    raw = _make_signal_raw(message_id="msg-99")
    assert resolver.resolve(raw, "signal") == resolver.resolve(raw, "signal")


def test_factory_produces_same_event_id_for_duplicate_delivery():
    factory = EventFactory(identity_resolver=EventIdentityResolver())
    raw = _make_signal_raw(message_id="msg-100")
    e1 = factory.create_event(raw, "signal")
    e2 = factory.create_event(raw, "signal")
    assert e1.event_id == e2.event_id
    assert len(e1.event_id) == 36  # fits String(36) durable column


def test_factory_without_resolver_keeps_distinct_uuid4():
    factory = EventFactory()  # default: no resolver -> backward compatible
    raw = _make_signal_raw(message_id="msg-101")
    assert factory.create_event(raw, "signal").event_id != factory.create_event(
        raw, "signal"
    ).event_id


def test_explicit_event_id_takes_precedence():
    factory = EventFactory(identity_resolver=EventIdentityResolver())
    raw = _make_signal_raw(message_id="msg-102")
    event = factory.create_event(raw, "signal", event_id="explicit-id-1")
    assert event.event_id == "explicit-id-1"


# ---------------------------------------------------------------------------
# 2. Source-specific identity is preserved exactly (native-ID sources)
# ---------------------------------------------------------------------------


def test_source_identity_preserved_atak_uid():
    raw = {"uid": "cot-uid-7", "type": "a-u-G", "lat": 50.0, "lon": 30.0}
    assert resolve_event_identity(raw, "atak") == resolve_event_identity(
        raw, "atak"
    )
    assert resolve_event_identity(raw, "atak") != resolve_event_identity(
        dict(raw, uid="cot-uid-8"), "atak"
    )


def test_source_identity_preserved_telegram_message_id():
    raw = {"chat_id": "-100123", "message_id": "42", "text": "x"}
    assert resolve_event_identity(raw, "telegram") == resolve_event_identity(
        raw, "telegram"
    )
    # Different message_id -> different identity.
    assert resolve_event_identity(raw, "telegram") != resolve_event_identity(
        dict(raw, message_id="43"), "telegram"
    )


# ---------------------------------------------------------------------------
# 3. Deterministic fallback for sources without native identity
# ---------------------------------------------------------------------------


def test_mqtt_deterministic_fallback_ignores_transport_metadata():
    raw = _make_mqtt_raw("sensor/temp", {"value": 22.5})
    raw_qos = dict(raw, qos=1, retain=True, client_id="c1")  # transport metadata
    assert resolve_event_identity(raw, "mqtt") == resolve_event_identity(
        raw_qos, "mqtt"
    )


def test_radio_deterministic_fallback_ignores_reception_metadata():
    raw = _make_radio_raw("145.500", "X1")
    raw_alt = dict(raw, signal_strength=90, modulation="FM", source="r2")
    assert resolve_event_identity(raw, "radio") == resolve_event_identity(
        raw_alt, "radio"
    )


def test_non_deduplicable_source_falls_back_to_uuid4():
    resolver = EventIdentityResolver()
    raw = {"anything": 1}
    # Unknown source has no policy -> None -> factory uses UUID4.
    assert resolver.resolve(raw, "unknown_source") is None
    factory = EventFactory(identity_resolver=resolver)
    assert factory.create_event(raw, "unknown_source").event_id != factory.create_event(
        raw, "unknown_source"
    ).event_id


# ---------------------------------------------------------------------------
# 4. Serialization round-trip preserves event_id
# ---------------------------------------------------------------------------


def test_serialization_round_trip_preserves_event_id():
    factory = EventFactory(identity_resolver=EventIdentityResolver())
    raw = _make_signal_raw(message_id="msg-200")
    event = factory.create_event(raw, "signal")
    restored = Event.from_dict(event.to_dict())
    assert restored.event_id == event.event_id


# ---------------------------------------------------------------------------
# End-to-end durable dedup on a real file-backed SQLite DB
# ---------------------------------------------------------------------------

_DB_FILE = None  # set per-test via a file fixture


def _fresh_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def _seed_durable_repo(db_path: str) -> SQLAlchemyEventRepository:
    """Reconfigure the global session manager to a file DB and init the repo."""
    configure_session_manager(f"sqlite:///{db_path}")
    manager = get_session_manager()
    repo = SQLAlchemyEventRepository(session_manager=manager)
    repo.initialize()
    return repo


def _count_durable_rows(repo: SQLAlchemyEventRepository, event_id: str) -> int:
    manager = repo.session_manager
    with manager.session() as session:
        rows = session.execute(
            text("SELECT count(*) FROM durable_canonical_events WHERE event_id=:e"),
            {"e": event_id},
        ).scalar()
    return int(rows or 0)


def _all_durable_event_ids(repo: SQLAlchemyEventRepository) -> list:
    manager = repo.session_manager
    with manager.session() as session:
        rows = session.execute(
            text("SELECT event_id FROM durable_canonical_events ORDER BY event_id")
        ).scalars()
    return list(rows)


def _close_global_manager():
    from app.database import session as _session_mod

    mgr = get_session_manager()
    if mgr is not None:
        try:
            mgr.close()
        except Exception:
            pass
    _session_mod._session_manager = None


@pytest.fixture()
def db_path():
    path = _fresh_db()
    yield path
    _close_global_manager()
    try:
        os.remove(path)
    except OSError:
        pass


def test_same_event_id_persisted_twice_yields_one_durable_row(db_path):
    repo = _seed_durable_repo(db_path)
    factory = EventFactory(identity_resolver=EventIdentityResolver())
    raw = _make_signal_raw(message_id="msg-300")
    event = factory.create_event(raw, "signal")

    repo.save(event)
    repo.save(event)  # duplicate of the same canonical event_id

    assert _count_durable_rows(repo, event.event_id) == 1


def test_duplicate_delivery_end_to_end_yields_one_row(db_path):
    """Same logical source message delivered twice through the real pipeline
    (via AdapterRuntime -> EventFactory -> EventPipeline -> durable repo)
    produces exactly one durable row."""
    from app.event_sources.adapters.base_adapter import BaseEventSourceAdapter
    from app.event_sources.runtime.adapter_runtime import AdapterRuntime

    repo = _seed_durable_repo(db_path)
    runtime = create_event_runtime()
    pipeline = runtime.pipeline
    factory = EventFactory(identity_resolver=EventIdentityResolver())

    class _SignalAdapter(BaseEventSourceAdapter):
        def __init__(self, raws):
            super().__init__()
            self._raws = list(raws)
            self._name = "signal"

        def source_name(self):
            return self._name

        def read_events(self):
            out, self._raws = self._raws, []
            return out

    raw = _make_signal_raw(message_id="msg-400")
    adapter = _SignalAdapter([raw, raw])
    rt = AdapterRuntime(adapter=adapter, factory=factory, pipeline=pipeline, name="signal")
    rt._process_raw(raw)
    rt._process_raw(raw)

    durable_repo = SQLAlchemyEventRepository(session_manager=get_session_manager())
    event_id = factory.create_event(raw, "signal").event_id
    assert _count_durable_rows(durable_repo, event_id) == 1


def test_two_concurrent_workers_same_event_id_one_row(db_path):
    """Two threads persisting the same event_id -> exactly one durable row,
    no IntegrityError surfaced as a failure."""
    repo = _seed_durable_repo(db_path)
    factory = EventFactory(identity_resolver=EventIdentityResolver())
    raw = _make_signal_raw(message_id="msg-500")
    event = factory.create_event(raw, "signal")

    results: list = []
    errors: list = []

    def worker():
        try:
            repo.save(event)
            results.append("ok")
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []  # duplicate save is idempotent, not an error
    assert _count_durable_rows(repo, event.event_id) == 1


def test_restart_reuses_same_event_id(db_path):
    """After a process-level 'restart' (new session manager over the same file
    DB), the same logical message still resolves to the same event_id and does
    not create a duplicate row."""
    repo = _seed_durable_repo(db_path)
    factory = EventFactory(identity_resolver=EventIdentityResolver())
    raw = _make_signal_raw(message_id="msg-600")
    event = factory.create_event(raw, "signal")
    repo.save(event)
    assert _count_durable_rows(repo, event.event_id) == 1

    # Simulate restart: drop the global manager, reconnect to the same file.
    _close_global_manager()
    repo2 = _seed_durable_repo(db_path)
    factory2 = EventFactory(identity_resolver=EventIdentityResolver())
    event2 = factory2.create_event(raw, "signal")
    assert event2.event_id == event.event_id

    repo2.save(event2)  # idempotent after restart
    assert _count_durable_rows(repo2, event2.event_id) == 1
    assert len(_all_durable_event_ids(repo2)) == 1


# ---------------------------------------------------------------------------
# 5. Single DB owner remains
# ---------------------------------------------------------------------------


def test_single_database_owner(db_path):
    repo = _seed_durable_repo(db_path)
    manager = get_session_manager()
    # Only one manager is in use for the durable path: the repository is bound
    # to the same global DatabaseSessionManager that owns the engine.
    assert repo.session_manager is manager
