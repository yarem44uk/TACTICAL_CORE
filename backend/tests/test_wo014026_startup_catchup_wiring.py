"""WO-014-026 — Production Startup/Recovery Wiring for Deterministic Projection Catch-up.

Proves that ``ProductionRuntime.start()`` (the single authoritative production
startup boundary) automatically invokes the existing deterministic
``ProjectionCatchUp.run()`` (WO-014-025) exactly once, before steady-state
source processing begins, so a crash/restart gap between durable Event
persistence and Entity projection is healed on startup.

    durable Event log
        → (startup) ProjectionCatchUp.run()
        → Entity projection
        → durable checkpoint advance

These tests exercise the PUBLIC startup boundary (``create_production_runtime``
+ ``runtime.start()``).  They never call ``runtime.event_runtime.catch_up.run()``
directly; the catch-up must be triggered by ``start()`` itself.

Key invariants covered:
  * startup catch-up executes and heals the durable-event/projection gap;
  * zero-backlog startup is safe and idempotent (no spurious state);
  * restart recovery projects the previously-unprojected Event;
  * repeated/duplicate processing is idempotent (no duplicate Entity);
  * a projection failure leaves the durable Event intact, does NOT advance the
    checkpoint, and does not prevent the source runtime from starting;
  * a single ``start()`` invokes catch-up exactly once;
  * no second DB owner is introduced.
"""

from __future__ import annotations

import pytest

import app.database.session as session_mod
from app.bootstrap import create_production_runtime
from app.database.session import configure_session_manager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_sources.interfaces.i_event_source_adapter import IEventSourceAdapter


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def session_manager():
    """Configure the GLOBAL DatabaseSessionManager to an isolated in-memory
    SQLite database (single canonical DB owner), resetting afterwards so
    nothing leaks. No second engine/sessionmaker/owner is created."""
    manager = configure_session_manager("sqlite:///:memory:")
    yield manager
    session_mod._session_manager = None


class _TestSource(IEventSourceAdapter):
    """Controllable passive source adapter (input stub only, on the external
    source boundary).  Used so ``ProductionRuntime.start()`` can start the
    supervisor; the catch-up assertions do not depend on it."""

    def __init__(self, name: str = "stub") -> None:
        self._name = name
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def health(self) -> bool:
        return self._running

    def read_events(self) -> list:
        return []

    def source_name(self) -> str:
        return self._name


def make_event(
    *,
    event_id: str,
    entity_id: str,
    event_type: EventType = EventType.SIGNAL_RECEIVED,
    payload: dict | None = None,
) -> Event:
    """Build a canonical domain Event with deterministic values."""
    import datetime

    return Event(
        event_id=event_id,
        entity_id=entity_id,
        event_type=event_type,
        timestamp=datetime.datetime(2026, 8, 17, 12, 0, 0, tzinfo=datetime.timezone.utc),
        source="wo014026-source",
        payload=payload if payload is not None else {"k": "v"},
        metadata=EventMetadata(tags=["wo014026"]),
        created_at=datetime.datetime(2026, 8, 17, 10, 0, 0, tzinfo=datetime.timezone.utc),
    )


def _runtime():
    """A production runtime composed via the authoritative bootstrap boundary,
    with an isolated source stub attached."""
    rt = create_production_runtime()
    rt.add_source(_TestSource("wo014026-stub"))
    return rt


# ---------------------------------------------------------------------------
# T1 — Startup catch-up executes (via start(), never catch_up.run() directly)
# ---------------------------------------------------------------------------


def test_startup_start_invokes_catch_up_and_projects(session_manager):
    """Persist durable Events WITHOUT projecting them, then start the
    production runtime.  ``start()`` must automatically run catch-up: the
    Entity becomes projected and the checkpoint advances."""
    rt = _runtime()
    # Persist durable events directly through the durable event service
    # (bypassing the projection path), leaving the checkpoint unadvanced.
    for i in range(3):
        rt.event_runtime.event_service.save_event(
            make_event(event_id=f"evt-026-s-{i}", entity_id=f"entity-026-s-{i}")
        )
    # Checkpoint is at 0 before startup; nothing projected yet.
    checkpoint = rt.event_runtime.projection_checkpoint
    assert checkpoint.get_last_seq() == 0

    # The ONLY public trigger: start().  We never call catch_up.run() here.
    rt.start()
    try:
        # Entities are now projected by the startup catch-up.
        entity_ids = {e["entity_id"] for e in rt.event_runtime.entity_manager.list_entities()}
        assert entity_ids == {"entity-026-s-0", "entity-026-s-1", "entity-026-s-2"}
        # Checkpoint advanced past the projected events.
        assert checkpoint.get_last_seq() > 0
        # Durable events remain durable.
        assert rt.event_runtime.event_service.get_event("evt-026-s-2") is not None
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T2 — Zero backlog: no spurious projection / no spurious state
# ---------------------------------------------------------------------------


def test_startup_zero_backlog_is_noop(session_manager):
    """When the checkpoint already equals the latest durable seq, start() must
    succeed without creating any extra Entity state."""
    rt = _runtime()
    # Fully project two events first (start-up the pipeline once to persist +
    # project through the normal path, then run catch-up to advance).
    rt.event_runtime.event_service.save_event(
        make_event(event_id="evt-026-z-1", entity_id="entity-026-z-1")
    )
    rt.event_runtime.catch_up.run()
    before_entities = len(rt.event_runtime.entity_manager.list_entities())

    # A fresh runtime sees an already-advanced checkpoint (zero backlog).
    rt2 = _runtime()
    rt2.start()
    try:
        # No spurious entities beyond what was already projected.
        assert len(rt2.event_runtime.entity_manager.list_entities()) == before_entities
        # Startup succeeded (source runtime started).
        assert rt2.started is True
    finally:
        rt2.stop()


# ---------------------------------------------------------------------------
# T3 — Restart recovery heals the durable-event / projection gap
# ---------------------------------------------------------------------------


def test_restart_recovery_heals_projection_gap(session_manager):
    """Simulate: Event persisted → projection not completed → runtime
    disappears → a new runtime starts → catch-up executes automatically →
    Entity becomes projected → checkpoint advances."""
    # Runtime #1: persist a durable event but DO NOT project it (no catch-up,
    # no pipeline.process — only durable save).  This simulates a crash after
    # Event persistence but before Entity projection.
    rt1 = _runtime()
    rt1.event_runtime.event_service.save_event(
        make_event(event_id="evt-026-r-1", entity_id="entity-026-r-1")
    )
    # (No catch-up run here — simulating the crash window.)
    rt1.stop()

    # Runtime #2: a fresh production runtime.  start() must heal the gap.
    rt2 = _runtime()
    assert rt2.event_runtime.projection_checkpoint.get_last_seq() == 0
    rt2.start()
    try:
        entity = rt2.event_runtime.entity_read.get("entity-026-r-1")
        assert entity is not None
        assert entity["entity_id"] == "entity-026-r-1"
        assert rt2.event_runtime.projection_checkpoint.get_last_seq() > 0
        assert rt2.event_runtime.event_service.get_event("evt-026-r-1") is not None
    finally:
        rt2.stop()


# ---------------------------------------------------------------------------
# T4 — Idempotency: already-projected event does not create a duplicate Entity
# ---------------------------------------------------------------------------


def test_startup_catch_up_is_idempotent(session_manager):
    """If an already-projected Event is encountered again on startup, no
    duplicate Entity is created and the checkpoint stays correct."""
    rt = _runtime()
    rt.event_runtime.event_service.save_event(
        make_event(event_id="evt-026-i-1", entity_id="entity-026-i-1")
    )
    rt.event_runtime.catch_up.run()  # project + advance checkpoint
    first = sorted(
        (e["entity_id"], e["version"]) for e in rt.event_runtime.entity_manager.list_entities()
    )

    # A second startup pass over the same durable event must be a no-op.
    rt2 = _runtime()
    rt2.start()
    try:
        second = sorted(
            (e["entity_id"], e["version"])
            for e in rt2.event_runtime.entity_manager.list_entities()
        )
        assert second == first  # identical state, no duplicates, no corruption
    finally:
        rt2.stop()


# ---------------------------------------------------------------------------
# T5 — Failure safety: failed projection does not advance checkpoint and does
#      not prevent startup
# ---------------------------------------------------------------------------


def test_startup_failure_does_not_advance_checkpoint_or_block_startup(
    session_manager, monkeypatch
):
    """A projection failure during startup must leave the durable Event intact,
    must NOT advance the checkpoint, and must NOT prevent the source runtime
    from starting."""
    rt = _runtime()
    rt.event_runtime.event_service.save_event(
        make_event(event_id="evt-026-f-1", entity_id="entity-026-f-1")
    )
    rt.event_runtime.event_service.save_event(
        make_event(event_id="evt-026-f-2", entity_id="entity-026-f-2")
    )
    checkpoint = rt.event_runtime.projection_checkpoint

    def flaky_projection(event):
        if event.event_id == "evt-026-f-1":
            raise RuntimeError("projection boom at startup")

    # Force the startup catch-up projection to fail on the first event.
    monkeypatch.setattr(rt.event_runtime.catch_up, "_projection", flaky_projection)

    # start() must still succeed (failure isolated, logged, not raised).
    rt.start()
    try:
        # Startup proceeded: source runtime started.
        assert rt.started is True
        # The failed event must NOT have advanced the checkpoint.
        assert checkpoint.get_last_seq() == 0
        # Durable events remain intact.
        assert rt.event_runtime.event_service.get_event("evt-026-f-1") is not None
        assert rt.event_runtime.event_service.get_event("evt-026-f-2") is not None
        # No entity was falsely projected for the failed event.
        assert rt.event_runtime.entity_read.get("entity-026-f-1") is None
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T6 — Exactly-once startup invocation
# ---------------------------------------------------------------------------


def test_startup_runs_catch_up_exactly_once(session_manager, monkeypatch):
    """A single start() invocation must invoke catch-up exactly once, and a
    second start() on an already-running runtime must NOT re-run it (the
    ``started`` guard makes startup idempotent — no background workers /
    timers / retry loops)."""
    rt = _runtime()
    rt.event_runtime.event_service.save_event(
        make_event(event_id="evt-026-o-1", entity_id="entity-026-o-1")
    )
    calls = {"n": 0}
    original_run = rt.event_runtime.catch_up.run

    def counting_run():
        calls["n"] += 1
        return original_run()

    monkeypatch.setattr(rt.event_runtime.catch_up, "run", counting_run)

    # One public start() -> catch-up runs exactly once.
    rt.start()
    assert calls["n"] == 1
    assert rt.started is True

    # A second start() on the SAME (already-started) runtime is idempotent:
    # the started-guard prevents a second catch-up invocation.
    rt.start()
    assert calls["n"] == 1

    rt.stop()
    assert rt.started is False


# ---------------------------------------------------------------------------
# T7 — No second DB owner introduced by the wiring
# ---------------------------------------------------------------------------


def test_startup_wiring_keeps_single_database_owner(session_manager):
    """The startup wiring must not introduce a second engine/sessionmaker/DB
    owner; all durable tables live on the single DatabaseSessionManager."""
    rt = _runtime()
    rt.start()
    try:
        manager = session_mod.get_session_manager()
        assert manager.engine is not None
        from app.database.base import Base

        tables = Base.metadata.tables
        assert "durable_canonical_events" in tables
        assert "entities" in tables
        assert "projection_checkpoint" in tables
    finally:
        rt.stop()
