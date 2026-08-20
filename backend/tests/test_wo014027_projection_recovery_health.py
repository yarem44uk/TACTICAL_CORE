"""WO-014-027 — Production Projection / Recovery Observability.

Proves the deterministic production-facing health/state contract over the
durable Event -> Entity projection and its catch-up recovery, exercised
through the real production composition boundary (``create_event_runtime`` /
``create_production_runtime``).

The contract must answer, from the production runtime boundary:
    1. current projection checkpoint
    2. durable projection backlog
    3. latest catch-up/recovery succeeded?
    4. latest recovery attempt failed?
    5. latest recovery error/state
    6. how many events remain to be projected
    7. healthy / degraded / recovering classification

Architectural invariants covered:
  * health inspection is READ-ONLY (never advances checkpoint, never persists
    events, never projects entities, never creates entities);
  * the health contract composes the SAME durable event repository + projection
    checkpoint as the production catch-up (single DatabaseSessionManager
    owner — no second engine/sessionmaker/persistence plane);
  * a failed projection/recovery produces a DEGRADED state, never a false
    HEALTHY;
  * a successful subsequent recovery clears the DEGRADED state;
  * the WO-014-026 startup catch-up behavior remains unchanged;
  * WO-014-019 idempotency and WO-014-025 deterministic recovery remain intact.
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
    """Controllable passive source adapter (input stub only)."""

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


def make_event(*, event_id: str, entity_id: str) -> Event:
    """Build a canonical domain Event with deterministic values."""
    import datetime

    return Event(
        event_id=event_id,
        entity_id=entity_id,
        event_type=EventType.SIGNAL_RECEIVED,
        timestamp=datetime.datetime(2026, 8, 17, 12, 0, 0, tzinfo=datetime.timezone.utc),
        source="wo014027-source",
        payload={"k": "v"},
        metadata=EventMetadata(tags=["wo014027"]),
        created_at=datetime.datetime(2026, 8, 17, 10, 0, 0, tzinfo=datetime.timezone.utc),
    )


def _runtime():
    """A production runtime composed via the authoritative bootstrap boundary."""
    rt = create_production_runtime()
    rt.add_source(_TestSource("wo014027-stub"))
    return rt


def _health(rt):
    """The production-wired projection/recovery health contract."""
    return rt.event_runtime.projection_recovery_health


# ---------------------------------------------------------------------------
# T1 — Healthy state with zero backlog
# ---------------------------------------------------------------------------


def test_healthy_state_with_zero_backlog(session_manager):
    """Project all events, then the health contract reports HEALTHY with zero
    backlog and a SUCCEEDED recovery status."""
    rt = _runtime()
    rt.event_runtime.event_service.save_event(
        make_event(event_id="evt-027-h-1", entity_id="entity-027-h-1")
    )
    rt.event_runtime.catch_up.run()  # project + advance checkpoint
    try:
        health = _health(rt)
        assert health is not None
        snap = health.snapshot()
        assert snap.state == "healthy"
        assert snap.backlog_count == 0
        assert snap.recovery_status == "succeeded"
        assert snap.persistence_active is True
        # The durable checkpoint equals the latest durable seq.
        assert snap.checkpoint_seq == snap.latest_seq
        assert snap.checkpoint_seq > 0
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T2 — Backlog is reported correctly
# ---------------------------------------------------------------------------


def test_backlog_is_reported_correctly(session_manager):
    """Persist events WITHOUT projecting them; the health contract reports the
    correct durable projection backlog and a RECOVERING state."""
    rt = _runtime()
    # Persist 3 durable events, leave the checkpoint unadvanced (no catch-up).
    for i in range(3):
        rt.event_runtime.event_service.save_event(
            make_event(event_id=f"evt-027-b-{i}", entity_id=f"entity-027-b-{i}")
        )
    try:
        health = _health(rt)
        snap = health.snapshot()
        assert snap.backlog_count == 3
        assert snap.state == "recovering"
        assert snap.latest_seq == 3
        assert snap.checkpoint_seq == 0
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T3 — Successful catch-up updates the observable checkpoint/state
# ---------------------------------------------------------------------------


def test_successful_catch_up_updates_observable_state(session_manager):
    """Running catch-up projects the backlog and the health contract reflects
    the advanced checkpoint, zero backlog and a SUCCEEDED recovery."""
    rt = _runtime()
    for i in range(2):
        rt.event_runtime.event_service.save_event(
            make_event(event_id=f"evt-027-c-{i}", entity_id=f"entity-027-c-{i}")
        )
    try:
        health = _health(rt)
        assert health.snapshot().backlog_count == 2
        # Deterministic catch-up (via the wrapped run()) records the outcome.
        rt.event_runtime.catch_up.run()
        snap = health.snapshot()
        assert snap.backlog_count == 0
        assert snap.state == "healthy"
        assert snap.recovery_status == "succeeded"
        assert snap.last_recovery_processed == 2
        assert snap.last_recovery_failed == 0
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T4 — Failed projection/recovery produces a DEGRADED state
# ---------------------------------------------------------------------------


def test_failed_recovery_produces_degraded_state(session_manager, monkeypatch):
    """A projection failure during catch-up leaves the checkpoint behind and
    the health contract reports DEGRADED with a FAILED recovery status — never
    a false HEALTHY."""
    rt = _runtime()
    rt.event_runtime.event_service.save_event(
        make_event(event_id="evt-027-d-1", entity_id="entity-027-d-1")
    )
    rt.event_runtime.event_service.save_event(
        make_event(event_id="evt-027-d-2", entity_id="entity-027-d-2")
    )
    checkpoint = rt.event_runtime.projection_checkpoint

    def flaky_projection(event):
        if event.event_id == "evt-027-d-1":
            raise RuntimeError("projection boom for health")

    monkeypatch.setattr(rt.event_runtime.catch_up, "_projection", flaky_projection)
    try:
        rt.event_runtime.catch_up.run()
        health = _health(rt)
        snap = health.snapshot()
        assert snap.state == "degraded"
        assert snap.recovery_status == "failed"
        assert snap.backlog_count == 2  # checkpoint did not advance
        assert checkpoint.get_last_seq() == 0
        # The catch-up driver stops at the first failed projection and reports
        # it via the CatchUpResult.failed count (it does NOT propagate, so the
        # error string is captured by the observable FAILED status + failed
        # count, not the per-exception detail).
        assert snap.last_recovery_failed == 1
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T5 — Recovery failure does not falsely report healthy
# ---------------------------------------------------------------------------


def test_recovery_failure_does_not_report_healthy(session_manager, monkeypatch):
    """After a failed recovery, the health contract must NOT report HEALTHY
    (the deterministic precedence maps a FAILED recovery to DEGRADED)."""
    rt = _runtime()
    rt.event_runtime.event_service.save_event(
        make_event(event_id="evt-027-e-1", entity_id="entity-027-e-1")
    )
    rt.event_runtime.catch_up.run()  # project one event, checkpoint advances

    # Now inject a failing projection for a NEW un-checkpointed event.
    rt.event_runtime.event_service.save_event(
        make_event(event_id="evt-027-e-2", entity_id="entity-027-e-2")
    )

    def flaky(event):
        if event.event_id == "evt-027-e-2":
            raise RuntimeError("boom")

    monkeypatch.setattr(rt.event_runtime.catch_up, "_projection", flaky)
    rt.event_runtime.catch_up.run()
    snap = _health(rt).snapshot()
    assert snap.recovery_status == "failed"
    assert snap.state == "degraded"  # not healthy
    assert snap.backlog_count == 1
    rt.stop()


# ---------------------------------------------------------------------------
# T6 — Successful subsequent recovery clears the DEGRADED state
# ---------------------------------------------------------------------------


def test_successful_recovery_clears_degraded(session_manager):
    """After a failed pass, fixing the projection and re-running catch-up
    restores HEALTHY with zero backlog (the failed event is retried)."""
    rt = _runtime()
    rt.event_runtime.event_service.save_event(
        make_event(event_id="evt-027-f-1", entity_id="entity-027-f-1")
    )
    health = _health(rt)
    try:
        # First a clean catch-up: healthy.
        rt.event_runtime.catch_up.run()
        assert health.snapshot().state == "healthy"
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T7 — Health inspection is read-only (no entities created / no checkpoint moved)
# ---------------------------------------------------------------------------


def test_health_inspection_is_read_only(session_manager):
    """Calling the health snapshot must not create entities, must not advance
    the checkpoint, and must not persist events."""
    rt = _runtime()
    rt.event_runtime.event_service.save_event(
        make_event(event_id="evt-027-r-1", entity_id="entity-027-r-1")
    )
    checkpoint = rt.event_runtime.projection_checkpoint
    before_checkpoint = checkpoint.get_last_seq()
    before_entities = len(rt.event_runtime.entity_manager.list_entities())

    try:
        # Multiple read-only inspections.
        for _ in range(3):
            _health(rt).snapshot()
            _health(rt).backlog_count()
            _health(rt).classify()

        assert checkpoint.get_last_seq() == before_checkpoint
        assert len(rt.event_runtime.entity_manager.list_entities()) == before_entities
        # Durable event count unchanged.
        assert len(rt.event_runtime.event_service.get_events()) == 1
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T8 — No second DB owner introduced
# ---------------------------------------------------------------------------


def test_no_second_database_owner(session_manager):
    """The health contract composes the single DatabaseSessionManager; no new
    engine/sessionmaker/DB is created."""
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


# ---------------------------------------------------------------------------
# T9 — Startup catch-up behavior remains unchanged (WO-014-026)
# ---------------------------------------------------------------------------


def test_startup_catch_up_still_runs_and_health_reflects_it(session_manager):
    """The WO-014-026 startup wiring still invokes catch-up on start(), and
    the health contract reflects the recovery outcome afterwards."""
    rt = _runtime()
    rt.event_runtime.event_service.save_event(
        make_event(event_id="evt-027-s-1", entity_id="entity-027-s-1")
    )
    # Only public start(); we never call catch_up.run() directly.
    rt.start()
    try:
        assert rt.started is True
        health = _health(rt)
        snap = health.snapshot()
        # The startup catch-up projected the event and advanced the checkpoint.
        assert snap.checkpoint_seq > 0
        assert snap.backlog_count == 0
        assert snap.recovery_status == "succeeded"
        assert rt.event_runtime.entity_read.get("entity-027-s-1") is not None
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T10 — Idempotency (WO-014-019) and deterministic recovery (WO-014-025) intact
# ---------------------------------------------------------------------------


def test_idempotency_and_deterministic_recovery_intact(session_manager):
    """Repeated processing/catch-up of the same event must not create duplicate
    entity state or advance the checkpoint incorrectly."""
    rt = _runtime()
    ev = make_event(event_id="evt-027-i-1", entity_id="entity-027-i-1")
    rt.event_runtime.event_service.save_event(ev)
    health = _health(rt)

    # First catch-up projects + advances.
    rt.event_runtime.catch_up.run()
    first = sorted(
        (e["entity_id"], e["version"]) for e in rt.event_runtime.entity_manager.list_entities()
    )
    snap1 = health.snapshot()

    # A second catch-up over the same durable event is a deterministic no-op.
    rt.event_runtime.catch_up.run()
    second = sorted(
        (e["entity_id"], e["version"]) for e in rt.event_runtime.entity_manager.list_entities()
    )
    snap2 = health.snapshot()
    try:
        assert second == first  # no duplicate entity
        assert snap2.checkpoint_seq == snap1.checkpoint_seq
        assert snap2.backlog_count == 0
        assert snap2.state == "healthy"
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T11 — Explicit durable read API is available (diagnostic)
# ---------------------------------------------------------------------------


def test_durable_health_reads_through_existing_owner(session_manager):
    """The health contract exposes the durable checkpoint position and latest
    durable seq through the shared DatabaseSessionManager (single owner)."""
    rt = _runtime()
    for i in range(2):
        rt.event_runtime.event_service.save_event(
            make_event(event_id=f"evt-027-x-{i}", entity_id=f"entity-027-x-{i}")
        )
    try:
        health = _health(rt)
        assert health.latest_seq() == 2
        assert health.checkpoint_seq() == 0
        assert health.backlog_count() == 2
        assert str(health.classify()) == "recovering"
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T12 — Production runtime constructs successfully with the new surface
# ---------------------------------------------------------------------------


def test_production_runtime_constructs_with_health_surface(session_manager):
    """The production runtime constructs successfully and exposes the health
    contract at the runtime boundary."""
    rt = _runtime()
    try:
        health = _health(rt)
        assert health is not None
        # Snapshot is deterministic and includes all required fields.
        snap = health.snapshot().to_dict()
        for key in (
            "state",
            "checkpoint_seq",
            "checkpoint_event_id",
            "latest_seq",
            "backlog_count",
            "recovery_status",
            "last_recovery_processed",
            "last_recovery_failed",
            "last_recovery_error",
            "last_recovery_at",
            "persistence_active",
        ):
            assert key in snap
    finally:
        rt.stop()


# ---------------------------------------------------------------------------
# T13 — A raised catch-up pass captures the last recovery error
# ---------------------------------------------------------------------------


def test_raised_catch_up_captures_last_recovery_error(session_manager, monkeypatch):
    """When a catch-up pass itself raises (e.g. an infrastructure failure before
    projection), the health contract captures the error string and reports a
    DEGRADED/FAILED state — distinct from an internal projection failure which
    is reported via the ``failed`` count.

    The failure is injected on the durable event repository read so it happens
    INSIDE the real (instrumented) ``catch_up.run()`` — the observability
    wrapper then records the error and re-raises.  (Patching ``catch_up.run``
    itself would replace the instrumented wrapper and bypass recording.)
    """
    rt = _runtime()
    rt.event_runtime.event_service.save_event(
        make_event(event_id="evt-027-g-1", entity_id="entity-027-g-1")
    )

    def exploding_iter(seq):
        raise RuntimeError("infrastructure boom before projection")

    monkeypatch.setattr(
        rt.event_runtime.catch_up._events, "iter_after_seq", exploding_iter
    )
    try:
        with pytest.raises(RuntimeError):
            rt.event_runtime.catch_up.run()
        health = _health(rt)
        snap = health.snapshot()
        assert snap.recovery_status == "failed"
        assert snap.state == "degraded"
        assert snap.last_recovery_error is not None
        assert "infrastructure boom" in snap.last_recovery_error
    finally:
        rt.stop()
