"""WO-015 — Observation canonical migration tests.

Verifies that ObservationService now consumes canonical ``app.event.event.Event``
objects through the canonical ``app.event_bus.event_bus.EventBus`` reached via
``EventPipeline.set_event_bus()``, and persists Observations through the real
production composition boundary.

Canonical production flow under test:

    canonical app.event.event.Event
        |
        v
    EventPipeline.process(event)
        |
        v
    durable Event repository        (unchanged)
        |
        v
    entity projection               (unchanged)
        |
        v
    canonical EventBus publish
        |
        v
    ObservationService._handle_canonical_event
        |
        v
    CanonicalEventToObservationAdapter
        |
        v
    ObservationProcessor
        |
        v
    Observation persistence        (single DatabaseSessionManager owner)

Tests use the real ``create_event_runtime()`` boundary where possible and avoid
mocking the critical persistence assertion.
"""

from datetime import datetime, timezone

import pytest

from app.database import session as session_mod
from app.database.session import configure_session_manager, get_session_manager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_bus.event_bus import EventBus
from app.observation.canonical_adapter import (
    CanonicalEventAdapterError,
    CanonicalEventToObservationAdapter,
)
from app.observation.service import ObservationService
from app.intelligence.observation.repository import ObservationRepository


@pytest.fixture()
def global_session_manager():
    """Configure the GLOBAL DatabaseSessionManager to an isolated in-memory
    SQLite database (exactly as the production app does at startup) and reset
    it afterwards so it does not leak across tests."""
    manager = configure_session_manager("sqlite:///:memory:")
    # Create all tables on the shared Base.metadata (observations, durable
    # events, entities, projection_checkpoint) — the single DB owner.  This
    # mirrors what the production composition's durable lifecycle guards
    # trigger via repository.initialize() / Base.metadata.create_all.
    from app.database.base import Base

    Base.metadata.create_all(manager.engine)
    yield manager
    session_mod._session_manager = None


def make_event(
    *,
    event_id: str,
    source: str = "signal",
    event_type: EventType = EventType.CUSTOM,
    payload: dict | None = None,
    metadata: EventMetadata | None = None,
) -> Event:
    """Build a canonical domain Event with deterministic values."""
    return Event(
        event_id=event_id,
        event_type=event_type,
        timestamp=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
        source=source,
        payload=payload or {},
        metadata=metadata or EventMetadata(),
    )


# ---------------------------------------------------------------------------
# Adapter contract
# ---------------------------------------------------------------------------


def test_adapter_signal_event_type_derivation():
    adapter = CanonicalEventToObservationAdapter()
    ev = make_event(event_id="e1", source="signal", payload={"message_id": "m1"})
    d = adapter.to_observation_dict(ev)
    assert d["event_type"] == "signal.message"
    assert d["source"] == "signal"
    assert d["data"]["message_id"] == "m1"
    assert d["event_id"] == "e1"


def test_adapter_protocol_event_types():
    adapter = CanonicalEventToObservationAdapter()
    cases = {
        "signal": "signal.message",
        "radio": "radio.transmission",
        "atak": "atak.map_object",
        "mqtt": "mqtt.message",
        "telegram": "telegram.message",
    }
    for source, expected in cases.items():
        d = adapter.to_observation_dict(make_event(event_id=f"e-{source}", source=source))
        assert d["event_type"] == expected, f"{source} -> {d['event_type']}"


def test_adapter_preserves_correlation_id():
    adapter = CanonicalEventToObservationAdapter()
    ev = make_event(
        event_id="e1",
        source="signal",
        payload={"message_id": "m1", "sender": "a", "chat_id": "c"},
        metadata=EventMetadata(correlation_id="corr-123", tags=["tag1"]),
    )
    d = adapter.to_observation_dict(ev)
    assert d["metadata"]["correlation_id"] == "corr-123"
    assert d["metadata"]["tags"] == ["tag1"]


def test_adapter_immutable_id_is_event_id():
    adapter = CanonicalEventToObservationAdapter()
    ev = make_event(event_id="immutable-id-xyz", source="signal", payload={"message_id": "m"})
    d = adapter.to_observation_dict(ev)
    assert d["event_id"] == "immutable-id-xyz"


def test_adapter_rejects_missing_event_id():
    adapter = CanonicalEventToObservationAdapter()
    with pytest.raises(CanonicalEventAdapterError):
        adapter.to_observation_dict(make_event(event_id=""))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Canonical EventBus + ObservationService wiring
# ---------------------------------------------------------------------------


def test_service_subscribes_canonical_custom():
    bus = EventBus()
    service = ObservationService(event_bus=None, session=None)
    sub = service.subscribe_canonical(bus)
    assert sub is not None
    assert service.canonical_subscription is sub
    assert bus.subscriber_count() == 1
    assert bus.get_subscribers(EventType.CUSTOM)  # subscribed to CUSTOM
    service.unsubscribe_canonical(bus)
    assert service.canonical_subscription is None


def test_service_handles_canonical_event(global_session_manager):
    service = ObservationService(event_bus=None, session=get_session_manager().get_session())
    ev = make_event(
        event_id="e-svc-1",
        source="signal",
        payload={"message_id": "m1", "sender": "alice", "chat_id": "c1"},
    )
    service._handle_canonical_event(ev)
    repo = ObservationRepository(get_session_manager().get_session())
    obs = repo.get_by_immutable_id("e-svc-1")
    assert obs is not None
    assert str(obs.immutable_id) == "e-svc-1"


# ---------------------------------------------------------------------------
# Production composition boundary
# ---------------------------------------------------------------------------


def test_production_composition_wires_observation(global_session_manager):
    from app.composition import create_event_runtime

    runtime = create_event_runtime()
    assert runtime.event_bus is not None
    assert runtime.observation_service is not None
    # pipeline has the canonical EventBus
    assert runtime.pipeline._event_bus is runtime.event_bus
    # observation service is subscribed to the canonical bus
    assert runtime.observation_service.canonical_subscription is not None


def test_production_pipeline_persists_observation(global_session_manager):
    from app.composition import create_event_runtime

    runtime = create_event_runtime()
    ev = make_event(
        event_id="e-prod-1",
        source="signal",
        payload={"message_id": "m1", "sender": "alice", "chat_id": "c1", "message_text": "hi"},
    )
    ok = runtime.pipeline.process(ev)
    assert ok is True

    repo = ObservationRepository(get_session_manager().get_session())
    obs = repo.get_by_immutable_id("e-prod-1")
    assert obs is not None
    assert obs.source == "signal"
    assert str(obs.immutable_id) == "e-prod-1"


def test_duplicate_canonical_event_no_duplicate_observation(global_session_manager):
    from app.composition import create_event_runtime

    runtime = create_event_runtime()
    ev = make_event(
        event_id="e-dup-1",
        source="signal",
        payload={"message_id": "m1", "sender": "alice", "chat_id": "c1"},
    )
    runtime.pipeline.process(ev)
    runtime.pipeline.process(ev)  # same event_id again

    repo = ObservationRepository(get_session_manager().get_session())
    obs = repo.get_by_immutable_id("e-dup-1")
    assert obs is not None
    # exactly one durable observation for this event_id
    matches = [
        o for o in repo.list_recent(limit=100) if str(o.immutable_id) == "e-dup-1"
    ]
    assert len(matches) == 1


def test_duplicate_event_does_not_poison_shared_observation_session(
    global_session_manager,
):
    """WO-015 defect regression: a duplicate event must not poison the shared
    SQLAlchemy Session held by the production ObservationService.

    A duplicate canonical event fires UNIQUE(immutable_id) IntegrityError at
    flush, which leaves the shared session in a rolled-back state.  Unless the
    service recovers the session, the next DISTINCT event fails to persist.
    This test uses ONE runtime (and therefore ONE long-lived observation
    session) for A, the duplicate of A, and a distinct B.
    """
    from app.composition import create_event_runtime

    runtime = create_event_runtime()
    ev_a = make_event(
        event_id="e-shared-a",
        source="signal",
        payload={"message_id": "m-a", "sender": "alice", "chat_id": "c"},
    )
    ev_b = make_event(
        event_id="e-shared-b",
        source="radio",
        payload={"frequency": 100.5, "callsign": "BRAVO"},
    )

    # 1. Process event A -> Observation A persisted.
    assert runtime.pipeline.process(ev_a) is True

    # 2. Process event A again -> duplicate, no second Observation, session
    #    must be recovered (this previously poisoned the shared session).
    assert runtime.pipeline.process(ev_a) is True

    # 3. Process DISTINCT event B through the SAME runtime / same session.
    assert runtime.pipeline.process(ev_b) is True

    # Final state: exactly two observations, one per distinct identity.
    repo = ObservationRepository(get_session_manager().get_session())
    rows = repo.list_recent(limit=100)
    ids = {str(o.immutable_id) for o in rows}
    assert ids == {"e-shared-a", "e-shared-b"}
    a_matches = [o for o in rows if str(o.immutable_id) == "e-shared-a"]
    b_matches = [o for o in rows if str(o.immutable_id) == "e-shared-b"]
    assert len(a_matches) == 1
    assert len(b_matches) == 1



@pytest.mark.parametrize(
    "source,payload",
    [
        ("signal", {"message_id": "m", "sender": "s", "chat_id": "c"}),
        ("mqtt", {"topic": "t", "payload": "p"}),
        ("radio", {"frequency": 100.5, "callsign": "ABC"}),
        ("telegram", {"chat_id": "c", "text": "hi"}),
        ("atak", {"uid": "u", "location": "1,2"}),
    ],
)
def test_production_pipeline_all_protocols(source, payload, global_session_manager):
    from app.composition import create_event_runtime

    runtime = create_event_runtime()
    ev = make_event(event_id=f"e-{source}-1", source=source, payload=payload)
    ok = runtime.pipeline.process(ev)
    assert ok is True
    repo = ObservationRepository(get_session_manager().get_session())
    obs = repo.get_by_immutable_id(f"e-{source}-1")
    assert obs is not None, f"no observation for {source}"


def test_observation_failure_isolated_from_pipeline(global_session_manager):
    from app.composition import create_event_runtime

    runtime = create_event_runtime()
    # A canonical event with no data -> observation mapping validation fails,
    # but the pipeline must still succeed (event durability is authoritative
    # and independent of observation projection).
    ev = make_event(event_id="e-fail-1", source="signal", payload={})
    ok = runtime.pipeline.process(ev)
    assert ok is True
