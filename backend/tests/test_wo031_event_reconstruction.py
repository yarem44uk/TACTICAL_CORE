"""WO-031 — Durable delivery event reconstruction.

WO-031 repairs the WO-027 durable-delivery consumer type mismatch.  Before
WO-031, ``DurableDeliveryDispatcher.deliver_pending()`` passed a
``DurableDeliveryRecord`` (delivery metadata: event_id, consumer_id, state,
attempts, timestamps) to the registered consumer callback.  Production
consumers require a canonical ``app.event.Event``:

    _deliver_plugins(event)      -> plugin_dispatcher.dispatch(event)
    _deliver_observation(event)  -> event_bus.publish(event)

Approved architecture decision (OPTION B): resolve ``record.event_id`` through
the existing durable canonical event repository and pass the reconstructed
canonical ``Event`` to the consumer callback.  The ``DurableDeliveryRecord``
remains delivery metadata only; the canonical event is never duplicated into
the outbox.

These tests exercise the REAL production path (real file-backed SQLite, real
durable event repository, real outbox repository, real dispatcher) with an
injected ``event_repository`` — matching what ``wire_durable_delivery()`` does
in production composition.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from typing import List, Optional

import pytest

import app.database.session as session_mod
from app.database.schema_migration import upgrade_schema
from app.database.session import configure_session_manager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_delivery.delivery_dispatcher import DurableDeliveryDispatcher
from app.event_delivery.outbox_model import DurableDeliveryRecord
from app.event_delivery.outbox_repository import SQLAlchemyOutboxRepository
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)


def make_event(event_id: str) -> Event:
    return Event(
        event_id=event_id,
        entity_id="entity-031",
        event_type=EventType.CUSTOM,
        timestamp=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
        source="wo031-source",
        payload={"k": "v"},
        metadata=EventMetadata(tags=["wo031"]),
        created_at=datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture()
def file_db():
    tmp = tempfile.mkdtemp(prefix="wo031-")
    db = os.path.join(tmp, "db.sqlite")
    configure_session_manager(f"sqlite:///{db}")
    upgrade_schema()
    yield db
    session_mod._session_manager = None


@pytest.fixture()
def outbox(file_db) -> SQLAlchemyOutboxRepository:
    o = SQLAlchemyOutboxRepository()
    o.initialize()
    return o


@pytest.fixture()
def repo(file_db) -> SQLAlchemyEventRepository:
    r = SQLAlchemyEventRepository()
    r.initialize()
    return r


def _delivered_dispatcher(
    repo: SQLAlchemyEventRepository,
    outbox: SQLAlchemyOutboxRepository,
) -> DurableDeliveryDispatcher:
    """A dispatcher wired like production (event_repository injected)."""
    return DurableDeliveryDispatcher(
        outbox_repository=outbox,
        event_repository=repo,
        max_attempts=3,
        backoff_base_seconds=0,
    )


# ---------------------------------------------------------------------------
# Core WO-031 invariants
# ---------------------------------------------------------------------------


def test_consumer_receives_canonical_event_not_record(repo, outbox):
    """deliver_pending() passes a canonical Event, NOT a DurableDeliveryRecord."""
    received: List[object] = []
    disp = _delivered_dispatcher(repo, outbox)

    def cb(payload: object) -> None:
        received.append(payload)

    disp.register_consumer("plugins", cb)
    # Persist a real durable canonical event + PENDING outbox record atomically.
    ev = make_event("evt-1")
    repo.save_with_deliveries(ev, ["plugins"])
    disp.deliver_pending()

    assert len(received) == 1
    payload = received[0]
    assert isinstance(payload, Event), (
        f"consumer must receive a canonical Event, got {type(payload).__name__}"
    )
    assert not isinstance(payload, DurableDeliveryRecord)
    assert payload.event_id == "evt-1"
    assert outbox.get_state("evt-1", "plugins") == "DELIVERED"


def test_event_id_preserved_exactly(repo, outbox):
    """The reconstructed Event preserves event_id byte-for-byte."""
    seen: List[str] = []
    disp = _delivered_dispatcher(repo, outbox)
    disp.register_consumer("plugins", lambda e: seen.append(e.event_id))
    repo.save_with_deliveries(make_event("evt-2"), ["plugins"])
    disp.deliver_pending()
    assert seen == ["evt-2"]
    # Persisted event_id is unchanged from the canonical event we stored.
    assert repo.get("evt-2").event_id == "evt-2"


def test_plugin_and_observation_consumers_receive_event(repo, outbox):
    """Both durable consumers (plugins + observation) receive the Event."""
    plugin_seen: List[str] = []
    obs_seen: List[str] = []
    disp = _delivered_dispatcher(repo, outbox)
    disp.register_consumer("plugins", lambda e: plugin_seen.append(e.event_id))
    disp.register_consumer("observation", lambda e: obs_seen.append(e.event_id))
    repo.save_with_deliveries(make_event("evt-3"), ["plugins", "observation"])
    disp.deliver_pending()

    assert plugin_seen == ["evt-3"]
    assert obs_seen == ["evt-3"]
    assert outbox.get_state("evt-3", "plugins") == "DELIVERED"
    assert outbox.get_state("evt-3", "observation") == "DELIVERED"


def test_missing_event_marks_failed_not_successful(repo, outbox):
    """A delivery whose canonical event cannot be found is FAILED, not DELIVERED,
    and does not invoke the consumer with None."""
    invoked: List[object] = []
    disp = _delivered_dispatcher(repo, outbox)
    disp.register_consumer("plugins", invoked.append)
    # Create the outbox record WITHOUT a corresponding canonical event.
    outbox.enqueue("evt-missing", "plugins")
    disp.deliver_pending()

    assert invoked == []  # consumer was never called with None / a bogus event
    assert outbox.get_state("evt-missing", "plugins") == "FAILED"


def test_missing_event_uses_existing_retry_mechanism(repo, outbox):
    """Once the canonical event appears, the previously-FAILED delivery is
    retried (WO-029 backoff) and reconstructed successfully."""
    disp = _delivered_dispatcher(repo, outbox)
    seen: List[str] = []
    disp.register_consumer("plugins", lambda e: seen.append(e.event_id))

    outbox.enqueue("evt-late", "plugins")
    disp.deliver_pending()
    assert outbox.get_state("evt-late", "plugins") == "FAILED"

    # The canonical event appears later (e.g. written by another process).
    repo.save_with_deliveries(make_event("evt-late"), ["plugins"])
    disp.deliver_pending()
    assert outbox.get_state("evt-late", "plugins") == "DELIVERED"
    assert seen == ["evt-late"]


def test_dead_letter_still_works_for_missing_event(repo, outbox):
    """A persistently missing event is retired to DEAD_LETTER after
    max_attempts (WO-029) — never marked successful, never crashes."""
    disp = DurableDeliveryDispatcher(
        outbox_repository=outbox,
        event_repository=repo,
        max_attempts=2,
        backoff_base_seconds=0,
    )
    disp.register_consumer("plugins", lambda e: None)
    outbox.enqueue("evt-dead", "plugins")
    for _ in range(3):  # exhaust max_attempts
        disp.deliver_pending()
    assert outbox.get_state("evt-dead", "plugins") == "DEAD_LETTER"


def test_record_based_path_preserved_without_repository(outbox):
    """When no event_repository is injected (lightweight/test dispatcher), the
    legacy record-based callback path is preserved unchanged."""
    received: List[str] = []
    disp = DurableDeliveryDispatcher(outbox_repository=outbox)
    disp.register_consumer("c1", lambda r: received.append(r.event_id))
    outbox.enqueue("evt-r", "c1")
    disp.deliver_pending()
    assert received == ["evt-r"]
    assert outbox.get_state("evt-r", "c1") == "DELIVERED"


def test_duplicate_consumer_isolation_and_idempotency(repo, outbox):
    """Independent consumers remain isolated; one failing consumer does not
    block the other, and DELIVERED is not redelivered."""
    plugin_ok: List[str] = []
    disp = _delivered_dispatcher(repo, outbox)

    def flaky(e: object) -> None:
        raise RuntimeError("transient")

    disp.register_consumer("plugins", flaky)
    disp.register_consumer("observation", lambda e: plugin_ok.append(e.event_id))
    repo.save_with_deliveries(make_event("evt-5"), ["plugins", "observation"])
    disp.deliver_pending()

    assert plugin_ok == ["evt-5"]  # observation delivered despite plugin failure
    assert outbox.get_state("evt-5", "plugins") == "FAILED"
    assert outbox.get_state("evt-5", "observation") == "DELIVERED"

    # A successful consumer is never redelivered.
    disp.deliver_pending()
    assert plugin_ok == ["evt-5"]
