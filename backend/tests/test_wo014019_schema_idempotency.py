"""
WO-014-019 tests: Schema Idempotency — Canonical Durable Event Identity.

Guarantees that database-level idempotency of canonical Event persistence is
enforced by the durable schema itself, not only by application-level existence
checks. The authoritative canonical identity is ``Event.event_id``; the durable
persistence representation must carry a persistent ``event_id`` with a
database-level UNIQUE guarantee, so that:

    save(Event(event_id="X"))
    save(Event(event_id="X"))

results in exactly one durable row with ``event_id = "X"``.

Tests verify against the REAL in-memory SQLite database (not only Python
metadata):

1. Unique event identity       — DB-level uniqueness on canonical event_id
2. Repository idempotency      — save(same) twice => count == 1
3. Different identities        — count == 2
4. Constraint in actual DB     — PRAGMA table_info / index_list / index_info
5. Database-native rejection   — a raw duplicate INSERT is rejected by the
                                 actual SQLite schema (not an app-level guard)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.database.session import DatabaseSessionManager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_repository.durable.durable_event_model import DurableCanonicalEvent
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.event_repository.interfaces.i_event_repository import IEventRepository


@pytest.fixture()
def session_manager() -> DatabaseSessionManager:
    """A fresh in-memory SQLite session manager for each test."""
    manager = DatabaseSessionManager(
        database_url="sqlite:///:memory:",
        echo=False,
    )
    manager.initialize()
    yield manager
    manager.close()


@pytest.fixture()
def repo(session_manager: DatabaseSessionManager) -> SQLAlchemyEventRepository:
    """A durable repository bound to an in-memory DB, table created."""
    repository = SQLAlchemyEventRepository(session_manager=session_manager)
    repository.initialize()
    return repository


def make_event(
    *,
    event_id: Optional[str] = None,
    source: str = "wo014019-source",
) -> Event:
    """Build a canonical domain Event with deterministic defaults."""
    return Event(
        event_id=event_id or "evt-wo014019-0000-0000-000000000000",
        entity_id=None,
        event_type=EventType.CUSTOM,
        timestamp=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
        source=source,
        payload={"k": "v"},
        metadata=EventMetadata(),
    )


# --------------------------------------------------------------------------
# Test 1 — Unique event identity (DB-level)
# --------------------------------------------------------------------------

def test_event_id_is_authoritative_durable_identity():
    """The durable table carries a persistent event_id with a UNIQUE guarantee,
    distinct from the surrogate ORM primary key."""
    table = DurableCanonicalEvent.__table__
    columns = {c.name: c for c in table.columns}

    # The legacy ORM PK `id` must NOT silently replace canonical event_id
    # semantics: event_id is a separate, DB-unique column, not the PK.
    assert "event_id" in columns
    assert "event_id" not in [c.name for c in table.primary_key.columns]
    assert columns["event_id"].unique is True


# --------------------------------------------------------------------------
# Test 2 — Repository idempotency: save twice => count == 1
# --------------------------------------------------------------------------

def test_repository_save_is_idempotent(repo: SQLAlchemyEventRepository):
    """save(event) twice yields exactly one durable record for that event_id."""
    event = make_event(event_id="X")
    repo.save(event)
    repo.save(event)
    assert repo.count() == 1
    got = repo.get("X")
    assert got is not None
    assert got.event_id == "X"


# --------------------------------------------------------------------------
# Test 3 — Different identities => count == 2
# --------------------------------------------------------------------------

def test_distinct_identities_produce_distinct_records(
    repo: SQLAlchemyEventRepository,
):
    """Persisting event_id X and event_id Y yields two durable records."""
    repo.save(make_event(event_id="X"))
    repo.save(make_event(event_id="Y"))
    assert repo.count() == 2
    assert repo.exists("X")
    assert repo.exists("Y")


# --------------------------------------------------------------------------
# Test 4 — Constraint exists in the ACTUAL database (PRAGMA inspection)
# --------------------------------------------------------------------------

def test_sqlite_schema_has_unique_event_id(
    session_manager: DatabaseSessionManager,
    repo: SQLAlchemyEventRepository,
):
    """The actual created SQLite table enforces UNIQUE on event_id.

    Uses PRAGMA table_info / index_list / index_info against the real engine,
    not merely Python metadata inspection. The table is created via the
    repository's initialize() (fixture) before inspection.
    """
    assert repo is not None  # ensures the durable table has been created
    with session_manager.engine.connect() as conn:
        # PRAGMA table_info: confirm the column exists and is not the PK.
        table_info = {
            row[1]: row for row in conn.execute(
                text("PRAGMA table_info(durable_canonical_events)")
            )
        }
    assert "event_id" in table_info, "event_id column absent from actual schema"
    # columns: cid, name, type, notnull, dflt_value, pk
    assert table_info["event_id"][5] == 0, "event_id must not be the surrogate PK"

    # Find the UNIQUE index that backs the constraint.
    with session_manager.engine.connect() as conn:
        index_rows = conn.execute(
            text("PRAGMA index_list(durable_canonical_events)")
        ).fetchall()
        unique_indexes = [r for r in index_rows if r[2] == 1]  # (seq,name,unique,...)

    assert unique_indexes, "expected at least one UNIQUE index in actual SQLite schema"

    unique_names = [r[1] for r in unique_indexes]
    found = False
    for name in unique_names:
        with session_manager.engine.connect() as conn:
            cols = [
                r[2]
                for r in conn.execute(
                    text(f"PRAGMA index_info({name!r})")
                ).fetchall()
            ]  # (seqno,cid,name,...)
        if "event_id" in cols:
            found = True
            break
    assert found, "no UNIQUE index over event_id in the actual SQLite schema"


# --------------------------------------------------------------------------
# Test 5 — Database-native rejection of a raw duplicate (schema enforcement)
# --------------------------------------------------------------------------

def test_database_rejects_duplicate_event_id(
    session_manager: DatabaseSessionManager,
    repo: SQLAlchemyEventRepository,
):
    """The actual schema rejects a duplicate canonical event_id on raw INSERT —
    proof the idempotency gate lives in the database, not in app code."""
    repo.save(make_event(event_id="X"))

    # Insert a second durable row with the same canonical event_id directly,
    # bypassing the repository entirely.
    with pytest.raises(IntegrityError):
        with session_manager.session(commit=True) as session:
            session.add(
                DurableCanonicalEvent(
                    event_id="X",
                    entity_id=None,
                    event_type=str(EventType.CUSTOM),
                    timestamp=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
                    source="raw-insert",
                    payload={},
                    event_metadata={},
                )
            )
            session.flush()

    # The repository-level duplicate save remains an idempotent no-op.
    repo.save(make_event(event_id="X"))
    assert repo.count() == 1
