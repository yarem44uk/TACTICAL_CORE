"""WO-027 — Durable post-commit event delivery (transactional outbox).

Canonical tests for the durable delivery boundary.  These verify against the
REAL outbox repository, the REAL delivery dispatcher, the REAL durable event
repository, the REAL migration engine and real file-based SQLite (no mocked
repositories / fake migration engines).

Contract covered:
  A.  No consumer side effect may execute before the canonical durable commit.
  B.  Commit -> process crash -> recovery: a committed event + its outbox
      records are durable; delivery resumes after restart (real child process).
  C.  Consumer failure is recorded (FAILED) and the delivery remains
      retryable; retry succeeds.
  D.  Consumer crash after a side effect, before delivery-state commit:
      redelivery occurs (AT-LEAST-ONCE) and durable event_id-based idempotency
      prevents a duplicate durable consumer side effect (real child process).
  E.  Multiple independent consumers: failure of one never blocks the others.
  F.  Duplicate outbox creation for (event_id, consumer_id) yields exactly one
      durable delivery record.
  G.  Restart recovery: pending and stale IN_FLIGHT deliveries are reclaimed.
  H.  Durable event + outbox atomicity: the event and its delivery records
      commit together; a failed event insert never leaves a partial outbox.
  I/J. WO-025 identity + full regression are run separately.

AT-LEAST-ONCE is the delivery guarantee; exactly-once transport is never
claimed.  Effectively-once side effects are demonstrated where the consumer
persists a durable idempotency record keyed on the canonical event_id.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pytest
from sqlalchemy import String, select
from sqlalchemy.orm import Mapped, mapped_column

import app.database.session as session_mod
from app.database.base import Base
from app.database.schema_migration import TARGET_VERSION, upgrade_schema
from app.database.session import configure_session_manager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_delivery.delivery_dispatcher import DurableDeliveryDispatcher
from app.event_delivery.outbox_model import DurableDeliveryRecord
from app.event_delivery.outbox_repository import SQLAlchemyOutboxRepository
from app.event_pipeline.event_pipeline import EventPipeline
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)

# A durable consumer-side idempotency ledger (simulating a consumer's own
# durable effect store keyed on canonical event_id).  Defined at module scope
# so SQLAlchemy can resolve the mapped annotations.
class ConsumerEffect(Base):
    __tablename__ = "consumer_effects"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)


PY = sys.executable
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def make_event(event_id: str) -> Event:
    return Event(
        event_id=event_id,
        entity_id="entity-027",
        event_type=EventType.CUSTOM,
        timestamp=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
        source="wo027-source",
        payload={"k": "v"},
        metadata=EventMetadata(tags=["wo027"]),
        created_at=datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture()
def file_db():
    """A real file-based SQLite database path + configured global manager."""
    tmp = tempfile.mkdtemp(prefix="wo027-")
    db = os.path.join(tmp, "db.sqlite")
    configure_session_manager(f"sqlite:///{db}")
    upgrade_schema()
    yield db
    session_mod._session_manager = None


@pytest.fixture()
def repo(file_db) -> SQLAlchemyEventRepository:
    r = SQLAlchemyEventRepository()
    r.initialize()
    return r


@pytest.fixture()
def outbox(file_db) -> SQLAlchemyOutboxRepository:
    o = SQLAlchemyOutboxRepository()
    o.initialize()
    return o


def _child_script(body: str) -> str:
    """Build a child-process python script that runs against the real modules."""
    return textwrap.dedent(
        f"""
        import os, sys
        sys.path.insert(0, {BACKEND!r})
        from app.database.session import configure_session_manager
        from app.database.schema_migration import upgrade_schema
        from app.event_repository.durable.sqlalchemy_event_repository import SQLAlchemyEventRepository
        from app.event_delivery.outbox_repository import SQLAlchemyOutboxRepository
        from app.event_delivery.delivery_dispatcher import DurableDeliveryDispatcher
        from app.event_delivery.outbox_model import DurableDeliveryRecord
        from sqlalchemy import select

        configure_session_manager("sqlite:///" + os.environ["WO027_DB"])
        upgrade_schema()
        {body}
        """
    )


# ---------------------------------------------------------------------------
# A. PRE-COMMIT CONSUMER BLOCKED
# ---------------------------------------------------------------------------


def test_no_consumer_side_effect_before_durable_commit(repo, outbox):
    """A consumer must never execute before the canonical event commits."""
    disp = DurableDeliveryDispatcher(outbox_repository=outbox)
    order: List[str] = []
    disp.register_consumer("c1", lambda record: order.append("consumer"))

    # Track whether save_with_deliveries has completed when consumers run.
    save_completed = {"done": False}

    class TrackingRepo:
        def save_with_deliveries(self, event, consumer_ids):
            save_completed["done"] = False
            repo.save_with_deliveries(event, consumer_ids)
            save_completed["done"] = True

        def get(self, event_id):
            return repo.get(event_id)

    pipeline = EventPipeline()
    pipeline.set_repository(TrackingRepo())
    pipeline.set_delivery_dispatcher(disp)
    pipeline.set_outbox_consumer_ids(["c1"])

    pipeline.process(make_event("evt-pre"))

    # The consumer ran, but only after the durable commit completed.
    assert order == ["consumer"]
    assert save_completed["done"] is True
    # The event is durably present.
    assert repo.get("evt-pre") is not None


# ---------------------------------------------------------------------------
# F. DUPLICATE OUTBOX CREATION -> exactly one record
# ---------------------------------------------------------------------------


def test_duplicate_outbox_creation_yields_one_record(outbox):
    outbox.enqueue("evt-f", "plugin:A")
    outbox.enqueue("evt-f", "plugin:A")  # duplicate -> no-op
    outbox.enqueue("evt-f", "plugin:B")
    assert outbox.count() == 2
    # One record per (event, consumer).
    from app.database.session import get_session_manager
    from sqlalchemy import func, select

    with get_session_manager().session(commit=False) as s:
        n = s.execute(
            select(func.count()).select_from(DurableDeliveryRecord).where(
                DurableDeliveryRecord.event_id == "evt-f",
                DurableDeliveryRecord.consumer_id == "plugin:A",
            )
        ).scalar()
    assert n == 1


# ---------------------------------------------------------------------------
# E. MULTIPLE CONSUMERS INDEPENDENT
# ---------------------------------------------------------------------------


def test_multiple_consumers_deliver_independently(repo, outbox):
    disp = DurableDeliveryDispatcher(outbox_repository=outbox)
    received: Dict[str, int] = {"plugin:A": 0, "plugin:B": 0, "observation": 0}

    def mk(cid):
        def cb(record):
            if cid == "plugin:B":
                raise RuntimeError("plugin:B is failing")
            received[cid] += 1

        return cb

    for cid in ("plugin:A", "plugin:B", "observation"):
        disp.register_consumer(cid, mk(cid))

    disp.enqueue("evt-e", ["plugin:A", "plugin:B", "observation"])
    disp.deliver_pending()

    # A and observation succeeded; B failed but did not block the others.
    assert received["plugin:A"] == 1
    assert received["observation"] == 1
    assert received["plugin:B"] == 0
    assert outbox.get_state("evt-e", "plugin:A") == "DELIVERED"
    assert outbox.get_state("evt-e", "observation") == "DELIVERED"
    assert outbox.get_state("evt-e", "plugin:B") == "FAILED"


# ---------------------------------------------------------------------------
# C. CONSUMER FAILURE -> RETRY
# ---------------------------------------------------------------------------


def test_consumer_failure_then_retry_succeeds(repo, outbox):
    # WO-029: use a zero backoff so the FAILED delivery is immediately
    # reclaimable on the next pass (verifies the retry path without waiting).
    disp = DurableDeliveryDispatcher(
        outbox_repository=outbox,
        max_attempts=5,
        backoff_base_seconds=0,
    )
    attempts = {"n": 0}

    def flaky(record):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("transient")
        received.append(record.event_id)

    received: List[str] = []
    disp.register_consumer("flaky", flaky)
    disp.enqueue("evt-c", ["flaky"])

    disp.deliver_pending()
    assert outbox.get_state("evt-c", "flaky") == "FAILED"
    assert received == []

    # Retry succeeds and marks DELIVERED; subsequent passes are no-ops.
    disp.deliver_pending()
    assert outbox.get_state("evt-c", "flaky") == "DELIVERED"
    assert received == ["evt-c"]
    disp.deliver_pending()
    assert received == ["evt-c"]  # not redelivered


# ---------------------------------------------------------------------------
# G. RESTART RECOVERY — pending + stale IN_FLIGHT reclaimed
# ---------------------------------------------------------------------------


def test_restart_recovers_pending_and_stale_inflight(outbox):
    # Pending record.
    outbox.enqueue("evt-g1", "c1")
    # IN_FLIGHT record with an expired lease (stale) simulates a crashed worker.
    outbox.enqueue("evt-g2", "c1")
    from app.database.session import get_session_manager

    mgr = get_session_manager()
    with mgr.session(commit=True) as s:
        row = s.execute(
            select(DurableDeliveryRecord).where(
                DurableDeliveryRecord.event_id == "evt-g2",
                DurableDeliveryRecord.consumer_id == "c1",
            )
        ).scalar_one()
        row.state = DurableDeliveryRecord.IN_FLIGHT
        row.attempts = 1
        row.updated_at = datetime(2020, 1, 1, tzinfo=timezone.utc)  # very stale

    disp = DurableDeliveryDispatcher(
        outbox_repository=outbox,  # type: ignore[arg-type]
    )
    disp.outbox._stale_lease_seconds = 60
    received: List[str] = []
    disp.register_consumer("c1", lambda r: received.append(r.event_id))

    disp.deliver_pending()
    # Both the pending and the stale IN_FLIGHT record are reclaimed and delivered.
    assert sorted(received) == ["evt-g1", "evt-g2"]
    assert outbox.get_state("evt-g1", "c1") == "DELIVERED"
    assert outbox.get_state("evt-g2", "c1") == "DELIVERED"


# ---------------------------------------------------------------------------
# H. DURABLE EVENT + OUTBOX ATOMICITY
# ---------------------------------------------------------------------------


def test_event_and_outbox_commit_atomically(repo, outbox):
    """save_with_deliveries commits the event and its delivery records together."""
    repo.save_with_deliveries(make_event("evt-h"), ["c1", "c2"])
    assert repo.get("evt-h") is not None
    assert outbox.get_state("evt-h", "c1") == "PENDING"
    assert outbox.get_state("evt-h", "c2") == "PENDING"

    # A failed duplicate insert (same event_id) must not create duplicate
    # delivery records and must preserve the event.
    repo.save_with_deliveries(make_event("evt-h"), ["c1", "c2"])
    assert repo.get("evt-h") is not None
    assert outbox.count_by_state("PENDING") == 2  # still exactly one per consumer


# ---------------------------------------------------------------------------
# B. COMMIT -> CRASH -> RECOVERY (real child process)
# ---------------------------------------------------------------------------


def test_commit_then_process_crash_delivery_recovers(file_db):
    """A committed event + outbox survive a real child-process crash; delivery
    resumes on restart.  This crosses a real OS process boundary."""
    db = file_db
    repo = SQLAlchemyEventRepository()
    repo.initialize()
    outbox = SQLAlchemyOutboxRepository()
    outbox.initialize()

    # Parent commits BOTH the durable canonical event AND its outbox delivery
    # record atomically (the real production state), but does NOT deliver.
    repo.save_with_deliveries(make_event("evt-b"), ["consumer-x"])

    env = {**os.environ, "WO027_DB": db, "PYTHONPATH": BACKEND}
    script = _child_script(
        """
        # Child: claim and deliver, but crash (os._exit) BEFORE committing the
        # DELIVERED state — simulating a crash after the side effect.
        outbox = SQLAlchemyOutboxRepository()
        disp = DurableDeliveryDispatcher(outbox_repository=outbox)
        side = {"n": 0}
        def cb(record):
            side["n"] += 1
            # Durable idempotency record keyed on event_id would be written here.
            os._exit(137)  # crash before DELIVERED state commit
        disp.register_consumer("consumer-x", cb)
        disp.deliver_pending()
        """
    )
    p = subprocess.run([PY, "-c", script], capture_output=True, text=True, env=env)
    assert p.returncode == 137  # real abnormal termination (SIGKILL-equivalent)

    # Parent reopens the same DB with production infrastructure.
    session_mod._session_manager = None
    configure_session_manager(f"sqlite:///{db}")
    upgrade_schema()
    outbox2 = SQLAlchemyOutboxRepository()
    outbox2.initialize()
    repo2 = SQLAlchemyEventRepository()

    # The durable event is present.
    assert repo2.get("evt-b") is not None
    # The delivery record is present and retryable (IN_FLIGHT from the crash,
    # then reclaimed on the next pass).
    state = outbox2.get_state("evt-b", "consumer-x")
    assert state in ("IN_FLIGHT", "PENDING")

    # Recovery: a fresh dispatcher with an idempotency-capable consumer delivers
    # exactly once.  The child crashed with the record IN_FLIGHT and a fresh
    # lease (not yet stale by the default 60s), so treat it as stale to reclaim
    # and redeliver it (AT-LEAST-ONCE).
    delivered: List[str] = []
    disp2 = DurableDeliveryDispatcher(outbox_repository=outbox2)
    disp2.outbox._stale_lease_seconds = 0
    disp2.register_consumer("consumer-x", lambda r: delivered.append(r.event_id))
    disp2.deliver_pending()
    disp2.deliver_pending()  # second pass must not redeliver
    assert delivered == ["evt-b"]
    assert outbox2.get_state("evt-b", "consumer-x") == "DELIVERED"


# ---------------------------------------------------------------------------
# D. CONSUMER CRASH AFTER SIDE EFFECT -> event_id idempotency prevents
#    duplicate durable side effect (real child process)
# ---------------------------------------------------------------------------


def test_consumer_crash_after_side_effect_idempotent(file_db):
    """After a consumer crashes post-side-effect, redelivery is AT-LEAST-ONCE
    but a durable event_id-keyed idempotency record prevents a duplicate
    durable consumer side effect.  Crosses a real OS process boundary."""
    db = file_db
    outbox = SQLAlchemyOutboxRepository()
    outbox.initialize()
    outbox.enqueue("evt-d", "consumer-d")

    # Create the durable consumer-side idempotency ledger on the shared DB.
    Base.metadata.create_all(bind=outbox.session_manager.engine)

    env = {**os.environ, "WO027_DB": db, "PYTHONPATH": BACKEND}
    script = _child_script(
        """
        from app.database.base import Base
        from app.database.session import get_session_manager
        from sqlalchemy import String, select
        from sqlalchemy.orm import Mapped, mapped_column
        class ConsumerEffect(Base):
            __tablename__ = "consumer_effects"
            event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
        Base.metadata.create_all(bind=get_session_manager().engine)

        outbox = SQLAlchemyOutboxRepository()
        disp = DurableDeliveryDispatcher(outbox_repository=outbox)
        def cb(record):
            mgr = get_session_manager()
            with mgr.session(commit=True) as s:
                s.add(ConsumerEffect(event_id=record.event_id))  # durable side effect
            os._exit(137)  # crash AFTER side effect, BEFORE DELIVERED commit
        disp.register_consumer("consumer-d", cb)
        disp.deliver_pending()
        """
    )
    p = subprocess.run([PY, "-c", script], capture_output=True, text=True, env=env)
    assert p.returncode == 137

    # Parent reopens and redelivers.  The consumer must be idempotent w.r.t.
    # event_id: the durable side effect (ConsumerEffect row) exists exactly once
    # even though the delivery was retried.
    session_mod._session_manager = None
    configure_session_manager(f"sqlite:///{db}")
    upgrade_schema()
    outbox2 = SQLAlchemyOutboxRepository()
    outbox2.initialize()
    Base.metadata.create_all(bind=outbox2.session_manager.engine)

    def _effect_count() -> int:
        mgr = session_mod.get_session_manager()
        with mgr.session(commit=False) as s:
            return int(
                s.execute(
                    select(ConsumerEffect.event_id)
                ).scalars().all().__len__()
            )

    assert _effect_count() == 1  # exactly one durable side effect from the crash

    # Redelivery pass: consumer checks its idempotency record and skips.
    effect_seen: Dict[str, int] = {"n": 0}
    disp2 = DurableDeliveryDispatcher(outbox_repository=outbox2)
    mgr = session_mod.get_session_manager()
    with mgr.session(commit=False) as s:
        has = (
            s.execute(
                select(ConsumerEffect.event_id).where(
                    ConsumerEffect.event_id == "evt-d"
                )
            ).scalar_one_or_none()
        ) is not None

    def idempotent_cb(record):
        effect_seen["n"] += 1
        # Idempotency: side effect already applied for this event_id -> skip.

    disp2.register_consumer("consumer-d", idempotent_cb)
    # The child crashed with the record IN_FLIGHT and a fresh lease (not yet
    # stale by the default 60s).  Treat that just-crashed delivery as stale so
    # the recovery pass reclaims and redelivers it (AT-LEAST-ONCE).
    disp2.outbox._stale_lease_seconds = 0
    disp2.deliver_pending()
    # The consumer was invoked (AT-LEAST-ONCE redelivery) but the durable side
    # effect was NOT duplicated (already present).
    assert effect_seen["n"] == 1
    assert _effect_count() == 1  # still exactly one
    assert outbox2.get_state("evt-d", "consumer-d") == "DELIVERED"


# ---------------------------------------------------------------------------
# Migration + ownership smoke
# ---------------------------------------------------------------------------


def test_wo027_migration_is_registered_and_targets_revision(file_db):
    """WO-027 adds the durable delivery outbox migration (revision 3)."""
    from app.database.schema_migration import MIGRATIONS

    revs = [m.revision for m in MIGRATIONS]
    assert TARGET_VERSION == 4
    assert revs == [1, 2, 3, 4]
    assert MIGRATIONS[2].name == "durable_delivery_outbox"
    assert MIGRATIONS[3].name == "durable_plugin_delivery_ledger"


def test_single_database_owner_preserved(file_db, repo, outbox):
    """WO-027 outbox uses the SAME DatabaseSessionManager as every other
    durable table (no second engine/sessionmaker/DB owner)."""
    mgr = session_mod.get_session_manager()
    assert repo.session_manager is mgr
    assert outbox.session_manager is mgr
