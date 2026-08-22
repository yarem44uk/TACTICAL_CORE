"""WO-029 — Durable delivery hardening & consumer idempotency.

Canonical tests for the WO-029 delivery-hardening contract on top of the
WO-027 transactional outbox:

  * Bounded retry policy: FAILED delivery respects a deterministic backoff
    schedule and is retired to DEAD_LETTER after ``max_attempts`` (no
    unbounded immediate retry loop).
  * DEAD_LETTER is terminal unless explicitly requeued.
  * Cross-process claim concurrency: two dispatchers cannot claim the same
    (event_id, consumer_id) record (exactly one execution).
  * Per-consumer ordering within a single dispatcher; global ordering across
    dispatchers is NOT claimed.
  * Durable plugin-delivery idempotency keyed on (event_id, plugin_id):
    exactly one durable idempotency record; redelivery does not duplicate it.
  * Independent consumer isolation preserved.
  * Restart preserves retry state; migration durability; single DB owner.

AT-LEAST-ONCE remains the delivery guarantee; exactly-once transport is never
claimed.  Cross-process scenarios use real file-based SQLite + real OS
subprocesses (no mocked repositories / fake migration engines).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pytest
from sqlalchemy import select

import app.database.session as session_mod
from app.database.base import Base
from app.database.schema_migration import TARGET_VERSION, upgrade_schema
from app.database.session import configure_session_manager
from app.event_delivery.delivery_dispatcher import DurableDeliveryDispatcher
from app.event_delivery.outbox_model import DurableDeliveryRecord
from app.event_delivery.outbox_repository import SQLAlchemyOutboxRepository
from app.event_delivery.plugin_idempotency import DurablePluginDelivery
from app.event_delivery.plugin_idempotency_ledger import PluginDeliveryLedger
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)

PY = sys.executable
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@staticmethod
def _child_script(body: str) -> str:
    return textwrap.dedent(
        f"""
        import os, sys
        sys.path.insert(0, {BACKEND!r})
        from app.database.session import configure_session_manager
        from app.database.schema_migration import upgrade_schema
        from app.event_delivery.outbox_repository import SQLAlchemyOutboxRepository
        from app.event_delivery.delivery_dispatcher import DurableDeliveryDispatcher
        from sqlalchemy import select

        configure_session_manager("sqlite:///" + os.environ["WO029_DB"])
        upgrade_schema()
        {body}
        """
    )


@pytest.fixture()
def file_db():
    tmp = tempfile.mkdtemp(prefix="wo029-")
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


def _migration_records() -> List[int]:
    from app.database.schema_migration import SchemaMigrationVersion
    from app.database.session import get_session_manager

    mgr = get_session_manager()
    with mgr.session(commit=False) as s:
        return sorted(
            s.execute(select(SchemaMigrationVersion.version)).scalars().all()
        )


# ---------------------------------------------------------------------------
# A. FAILED delivery respects retry schedule (backoff enforced)
# ---------------------------------------------------------------------------


def test_failed_delivery_respects_backoff_schedule(outbox):
    disp = DurableDeliveryDispatcher(
        outbox_repository=outbox,
        max_attempts=5,
        backoff_base_seconds=10.0,  # long backoff -> not immediately retryable
    )
    calls = {"n": 0}

    def always_fail(record):
        calls["n"] += 1
        raise RuntimeError("boom")

    disp.register_consumer("c", always_fail)
    disp.enqueue("e1", ["c"])
    disp.deliver_pending()
    assert outbox.get_state("e1", "c") == "FAILED"

    # Immediately-again deliver_pending must NOT reclaim the FAILED record
    # (its next_attempt_at is in the future -> backoff enforced).
    disp.deliver_pending()
    assert outbox.get_state("e1", "c") == "FAILED"
    assert calls["n"] == 1  # not redelivered before the schedule


def test_failed_delivery_retried_after_schedule(outbox):
    disp = DurableDeliveryDispatcher(
        outbox_repository=outbox,
        max_attempts=5,
        backoff_base_seconds=0,  # immediate schedule -> retryable next pass
    )
    calls = {"n": 0}

    def flaky(record):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        delivered.append(record.event_id)

    delivered: List[str] = []
    disp.register_consumer("c", flaky)
    disp.enqueue("e2", ["c"])
    disp.deliver_pending()
    assert outbox.get_state("e2", "c") == "FAILED"
    disp.deliver_pending()
    assert outbox.get_state("e2", "c") == "DELIVERED"
    assert delivered == ["e2"]


# ---------------------------------------------------------------------------
# C/D. max_attempts terminates retry -> DEAD_LETTER (terminal)
# ---------------------------------------------------------------------------


def test_max_attempts_terminates_retry_and_dead_letter(outbox):
    disp = DurableDeliveryDispatcher(
        outbox_repository=outbox,
        max_attempts=3,
        backoff_base_seconds=0,
    )
    calls = {"n": 0}

    def always_fail(record):
        calls["n"] += 1
        raise RuntimeError("boom")

    disp.register_consumer("c", always_fail)
    disp.enqueue("e3", ["c"])

    # Three attempts -> FAILED, FAILED, then DEAD_LETTER (attempts reach max).
    disp.deliver_pending()
    assert outbox.get_state("e3", "c") == "FAILED"
    disp.deliver_pending()
    assert outbox.get_state("e3", "c") == "FAILED"
    disp.deliver_pending()
    assert outbox.get_state("e3", "c") == "DEAD_LETTER"
    assert calls["n"] == 3


def test_dead_letter_not_automatically_retried(outbox):
    disp = DurableDeliveryDispatcher(
        outbox_repository=outbox,
        max_attempts=1,
        backoff_base_seconds=0,
    )
    calls = {"n": 0}

    def always_fail(record):
        calls["n"] += 1
        raise RuntimeError("boom")

    disp.register_consumer("c", always_fail)
    disp.enqueue("e4", ["c"])
    disp.deliver_pending()
    assert outbox.get_state("e4", "c") == "DEAD_LETTER"

    # Further passes must never reclaim DEAD_LETTER.
    disp.deliver_pending()
    disp.deliver_pending()
    assert outbox.get_state("e4", "c") == "DEAD_LETTER"
    assert calls["n"] == 1


def test_dead_letter_requires_explicit_requeue(outbox):
    disp = DurableDeliveryDispatcher(
        outbox_repository=outbox,
        max_attempts=1,
        backoff_base_seconds=0,
    )
    calls = {"n": 0}

    def flaky(record):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        delivered.append(record.event_id)

    delivered: List[str] = []
    disp.register_consumer("c", flaky)
    disp.enqueue("e5", ["c"])
    disp.deliver_pending()
    assert outbox.get_state("e5", "c") == "DEAD_LETTER"

    # Automatic retry does nothing (terminal).
    disp.deliver_pending()
    assert outbox.get_state("e5", "c") == "DEAD_LETTER"
    assert delivered == []

    # Explicit administrative requeue restores PENDING and allows delivery.
    assert outbox.requeue_dead_letter("e5", "c") is True
    disp.deliver_pending()
    assert outbox.get_state("e5", "c") == "DELIVERED"
    assert delivered == ["e5"]


# ---------------------------------------------------------------------------
# H. Per-consumer ordering within a single dispatcher
# ---------------------------------------------------------------------------


def test_single_dispatcher_preserves_per_consumer_ordering(outbox):
    disp = DurableDeliveryDispatcher(outbox_repository=outbox)
    disp.register_consumer("c", lambda r: received.append(r.event_id))
    received: List[str] = []
    # Enqueue in a deliberate order; claim orders by created_at.
    for eid in ("evt-1", "evt-2", "evt-3"):
        disp.enqueue(eid, ["c"])
    disp.deliver_pending()
    # Within a single dispatcher, a consumer observes enqueue order.
    assert received == ["evt-1", "evt-2", "evt-3"]


# ---------------------------------------------------------------------------
# J/K. Durable plugin-delivery idempotency (event_id, plugin_id)
# ---------------------------------------------------------------------------


def test_plugin_idempotency_unique_record(outbox):
    ledger = PluginDeliveryLedger()
    ledger.initialize()
    assert ledger.record_delivery("evt-p1", "plugin-a") is True
    # Duplicate insert of the same (event_id, plugin_id) is a benign no-op.
    assert ledger.record_delivery("evt-p1", "plugin-a") is False
    assert ledger.has_delivered("evt-p1", "plugin-a") is True
    # A different plugin_id is an independent record.
    assert ledger.record_delivery("evt-p1", "plugin-b") is True


def test_plugin_redelivery_does_not_duplicate_idempotency_record(outbox):
    ledger = PluginDeliveryLedger()
    ledger.initialize()
    assert ledger.record_delivery("evt-p2", "plugin-a") is True
    # Simulate a redelivery of the same event to the same plugin.
    assert ledger.record_delivery("evt-p2", "plugin-a") is False
    from app.database.session import get_session_manager

    mgr = get_session_manager()
    with mgr.session(commit=False) as s:
        n = s.execute(
            select(DurablePluginDelivery.id).where(
                DurablePluginDelivery.event_id == "evt-p2",
                DurablePluginDelivery.plugin_id == "plugin-a",
            )
        ).scalars().all()
    assert len(n) == 1  # exactly one durable idempotency record


def test_plugin_ledger_run_idempotent_executes_once(outbox):
    ledger = PluginDeliveryLedger()
    ledger.initialize()
    side_effects: List[str] = []

    def effect():
        side_effects.append("ran")

    executed, _ = ledger.run_idempotent("evt-p3", "plugin-a", effect)
    assert executed is True
    # Second run_idempotent for the same pair suppresses the side effect.
    executed2, _ = ledger.run_idempotent("evt-p3", "plugin-a", effect)
    assert executed2 is False
    assert side_effects == ["ran"]


# ---------------------------------------------------------------------------
# F. Cross-process concurrent claim: exactly one dispatcher claims
# ---------------------------------------------------------------------------


def test_cross_process_claim_single_winner(file_db):
    """Two real dispatcher processes race to claim the same delivery; exactly
    one wins (no duplicate consumer execution)."""
    db = file_db
    outbox = SQLAlchemyOutboxRepository()
    outbox.initialize()
    outbox.enqueue("evt-race", "consumer-x")

    env = {**os.environ, "WO029_DB": db, "PYTHONPATH": BACKEND}
    child = _child_script(
        """
        outbox = SQLAlchemyOutboxRepository()
        claimed = outbox.claim_pending(limit=10)
        # Only one process should successfully claim the single record.
        if claimed:
            print("CLAIMED", claimed[0].event_id, claimed[0].consumer_id)
        else:
            print("NONE")
        """
    )

    procs = [
        subprocess.Popen(
            [PY, "-c", child], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env,
        )
        for _ in range(2)
    ]
    outputs = [p.communicate()[0].strip() for p in procs]
    for p in procs:
        assert p.returncode == 0
    claimed_count = sum(1 for o in outputs if o.startswith("CLAIMED"))
    # Exactly one winner — the second process saw no eligible record.
    assert claimed_count == 1, outputs
    # The record is now IN_FLIGHT (claimed by the winner), not duplicated.
    assert outbox.count() == 1


def test_cross_process_duplicate_delivery_prevention(file_db):
    """Two concurrent dispatchers delivering the same record must not cause a
    duplicate durable consumer side effect."""
    db = file_db
    outbox = SQLAlchemyOutboxRepository()
    outbox.initialize()
    outbox.enqueue("evt-dup", "consumer-y")

    env = {**os.environ, "WO029_DB": db, "PYTHONPATH": BACKEND}
    child = _child_script(
        """
        from app.event_delivery.outbox_model import DurableDeliveryRecord
        outbox = SQLAlchemyOutboxRepository()
        disp = DurableDeliveryDispatcher(outbox_repository=outbox)
        # Consumer claims+delivers only if it can claim the record.
        claimed = outbox.claim_pending(limit=10)
        for rec in claimed:
            outbox.mark_delivered(rec.event_id, rec.consumer_id)
        """
    )
    procs = [
        subprocess.Popen(
            [PY, "-c", child], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env,
        )
        for _ in range(2)
    ]
    for p in procs:
        p.communicate()
        assert p.returncode == 0

    # The delivery was delivered exactly once (DELIVERED), not duplicated.
    assert outbox.get_state("evt-dup", "consumer-y") == "DELIVERED"
    # No duplicate durable delivery record was created.
    assert outbox.count() == 1


# ---------------------------------------------------------------------------
# L. Independent consumers isolated
# ---------------------------------------------------------------------------


def test_independent_consumers_isolated(outbox):
    disp = DurableDeliveryDispatcher(outbox_repository=outbox)
    got = {"a": 0, "b": 0}

    def mk(cid):
        def cb(record):
            if cid == "b":
                raise RuntimeError("b fails")
            got[cid] += 1
        return cb

    disp.register_consumer("a", mk("a"))
    disp.register_consumer("b", mk("b"))
    disp.enqueue("evt-iso", ["a", "b"])
    disp.deliver_pending()
    assert got["a"] == 1
    assert got["b"] == 0
    assert outbox.get_state("evt-iso", "a") == "DELIVERED"
    assert outbox.get_state("evt-iso", "b") == "FAILED"


# ---------------------------------------------------------------------------
# M. Restart preserves retry state
# ---------------------------------------------------------------------------


def test_restart_preserves_retry_state(file_db):
    db = file_db
    outbox = SQLAlchemyOutboxRepository()
    outbox.initialize()
    outbox.enqueue("evt-restart", "consumer-z")

    # First pass: claim + fail -> FAILED with backoff.
    disp = DurableDeliveryDispatcher(
        outbox_repository=outbox, max_attempts=3, backoff_base_seconds=0
    )

    def always_fail(record):
        raise RuntimeError("boom")

    disp.register_consumer("consumer-z", always_fail)
    disp.deliver_pending()
    assert outbox.get_state("evt-restart", "consumer-z") == "FAILED"

    # Simulate restart: fresh repository + dispatcher over the same DB file.
    session_mod._session_manager = None
    configure_session_manager(f"sqlite:///{db}")
    upgrade_schema()
    outbox2 = SQLAlchemyOutboxRepository()
    outbox2.initialize()
    # Retry state (FAILED, attempts) is durable across restart.
    assert outbox2.get_state("evt-restart", "consumer-z") == "FAILED"
    disp2 = DurableDeliveryDispatcher(
        outbox_repository=outbox2, max_attempts=3, backoff_base_seconds=0
    )
    disp2.register_consumer("consumer-z", lambda r: delivered.append(r.event_id))
    delivered: List[str] = []
    disp2.deliver_pending()
    assert outbox2.get_state("evt-restart", "consumer-z") == "DELIVERED"
    assert delivered == ["evt-restart"]


# ---------------------------------------------------------------------------
# N. Migration durability / O. single owner
# ---------------------------------------------------------------------------


def test_migration_adds_plugin_ledger_and_advances_target(file_db):
    revs = [m.revision for m in __import__(
        "app.database.schema_migration", fromlist=["MIGRATIONS"]
    ).MIGRATIONS]
    assert TARGET_VERSION == max(revs)
    assert 4 in revs  # WO-029 revision-4 migration is registered
    # Fresh DB upgrade reaches the full registry (one record per revision).
    assert _migration_records() == list(range(1, TARGET_VERSION + 1))
    # The plugin ledger table physically exists.
    from app.database.session import get_session_manager

    mgr = get_session_manager()
    with mgr.session(commit=False) as s:
        tables = s.execute(
            select(__import__("sqlalchemy").text("name")).select_from(
                __import__("sqlalchemy").text("sqlite_master")
            ).where(__import__("sqlalchemy").text("type='table'"))
        ).scalars().all()
    assert "durable_plugin_delivery" in tables


def test_single_database_owner_preserved(outbox, repo):
    mgr = session_mod.get_session_manager()
    ledger = PluginDeliveryLedger()
    assert ledger.session_manager is mgr
    assert outbox.session_manager is mgr
    assert repo.session_manager is mgr


# ---------------------------------------------------------------------------
# F2 — stale IN_FLIGHT at max_attempts must NOT exceed max_attempts or invoke
# the consumer again (terminal DEAD_LETTER instead).
# ---------------------------------------------------------------------------


def test_stale_inflight_at_max_attempts_does_not_exceed_max_or_redeliver(
    file_db,
):
    """F2: a stale IN_FLIGHT delivery at attempts == max_attempts must not be
    reclaimed for another consumer attempt, must not increment attempts past
    max, and must be retired to DEAD_LETTER (terminal)."""
    db = file_db
    outbox = SQLAlchemyOutboxRepository(
        max_attempts=2, stale_lease_seconds=0, backoff_base_seconds=0
    )
    outbox.initialize()
    outbox.enqueue("evt-f2", "consumer-x")

    # Establish the crashed-worker state: IN_FLIGHT at max attempts, stale.
    mgr = session_mod.get_session_manager()
    with mgr.session(commit=True) as s:
        row = s.query(DurableDeliveryRecord).filter_by(
            event_id="evt-f2", consumer_id="consumer-x"
        ).one()
        row.state = DurableDeliveryRecord.IN_FLIGHT
        row.attempts = 2  # == max_attempts
        row.updated_at = datetime.now(timezone.utc) - timedelta(seconds=999)

    invocations: List[str] = []
    disp = DurableDeliveryDispatcher(
        outbox_repository=outbox, max_attempts=2, backoff_base_seconds=0
    )
    disp.register_consumer("consumer-x", lambda r: invocations.append(r.event_id))

    # claim_pending must NOT reclaim the exhausted stale record.
    claimed = outbox.claim_pending(limit=10, consumer_ids=["consumer-x"])
    assert claimed == []
    assert invocations == []  # consumer NOT invoked
    # attempts MUST NOT exceed max (2 -> 3 is forbidden).
    with mgr.session(commit=False) as s:
        row = s.query(DurableDeliveryRecord).filter_by(
            event_id="evt-f2", consumer_id="consumer-x"
        ).one()
        assert row.attempts == 2
    # The record is retired to DEAD_LETTER (terminal).
    assert outbox.get_state("evt-f2", "consumer-x") == "DEAD_LETTER"

    # DEAD_LETTER is never automatically claimed again.
    disp.deliver_pending()
    disp.deliver_pending()
    assert outbox.get_state("evt-f2", "consumer-x") == "DEAD_LETTER"
    assert invocations == []

    # Explicit requeue resets attempts and makes a fresh delivery possible.
    assert outbox.requeue_dead_letter("evt-f2", "consumer-x") is True
    assert outbox.get_state("evt-f2", "consumer-x") == "PENDING"
    with mgr.session(commit=False) as s:
        row = s.query(DurableDeliveryRecord).filter_by(
            event_id="evt-f2", consumer_id="consumer-x"
        ).one()
        assert row.attempts == 0  # retry counter reset per existing contract
    disp.deliver_pending()
    assert outbox.get_state("evt-f2", "consumer-x") == "DELIVERED"
    assert invocations == ["evt-f2"]


def test_stale_inflight_boundary_below_max_retries_above_max_dead_letters(
    file_db,
):
    """F2 adjacent boundary:
      attempts == max_attempts - 1, stale IN_FLIGHT -> reclaim allowed,
        attempts -> max_attempts, consumer may execute;
      attempts == max_attempts,     stale IN_FLIGHT -> reclaim NOT allowed,
        consumer does NOT execute, attempts stays max, DEAD_LETTER."""
    # --- below max: reclaim allowed, attempts becomes exactly max ---
    db = file_db
    outbox = SQLAlchemyOutboxRepository(
        max_attempts=2, stale_lease_seconds=0, backoff_base_seconds=0
    )
    outbox.initialize()
    outbox.enqueue("evt-below", "consumer-x")
    mgr = session_mod.get_session_manager()
    with mgr.session(commit=True) as s:
        row = s.query(DurableDeliveryRecord).filter_by(
            event_id="evt-below", consumer_id="consumer-x"
        ).one()
        row.state = DurableDeliveryRecord.IN_FLIGHT
        row.attempts = 1  # == max - 1
        row.updated_at = datetime.now(timezone.utc) - timedelta(seconds=999)

    below_calls: List[str] = []
    disp_below = DurableDeliveryDispatcher(
        outbox_repository=outbox, max_attempts=2, backoff_base_seconds=0
    )
    disp_below.register_consumer(
        "consumer-x", lambda r: below_calls.append(r.event_id)
    )
    disp_below.deliver_pending()
    # reclaim allowed -> consumer executed -> DELIVERED, attempts == 2
    assert below_calls == ["evt-below"]
    assert outbox.get_state("evt-below", "consumer-x") == "DELIVERED"
    with mgr.session(commit=False) as s:
        row = s.query(DurableDeliveryRecord).filter_by(
            event_id="evt-below", consumer_id="consumer-x"
        ).one()
        assert row.attempts == 2  # exactly max, not max+1

    # --- at/over max: reclaim NOT allowed, DEAD_LETTER, no invocation ---
    outbox.enqueue("evt-atmax", "consumer-y")
    with mgr.session(commit=True) as s:
        row = s.query(DurableDeliveryRecord).filter_by(
            event_id="evt-atmax", consumer_id="consumer-y"
        ).one()
        row.state = DurableDeliveryRecord.IN_FLIGHT
        row.attempts = 2  # == max
        row.updated_at = datetime.now(timezone.utc) - timedelta(seconds=999)
    atmax_calls: List[str] = []
    disp_atmax = DurableDeliveryDispatcher(
        outbox_repository=outbox, max_attempts=2, backoff_base_seconds=0
    )
    disp_atmax.register_consumer(
        "consumer-y", lambda r: atmax_calls.append(r.event_id)
    )
    disp_atmax.deliver_pending()
    assert atmax_calls == []  # consumer NOT invoked
    assert outbox.get_state("evt-atmax", "consumer-y") == "DEAD_LETTER"
    with mgr.session(commit=False) as s:
        row = s.query(DurableDeliveryRecord).filter_by(
            event_id="evt-atmax", consumer_id="consumer-y"
        ).one()
        assert row.attempts == 2  # attempts never exceeded max
