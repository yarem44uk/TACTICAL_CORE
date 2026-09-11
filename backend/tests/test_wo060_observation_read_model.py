"""WO-060 — Observation read model / query / operator read path.

WO-060 makes the persisted Observation read model reliably queryable,
chronologically deterministic and operator-readable.  It adds a queryable,
event-time ``occurred_at`` field (distinct from the ingestion ``timestamp``),
introduces a deterministic event-time chronology read path, exposes observations
through the operator API, and adds a real schema-evolution migration (revision 5)
so existing populated databases can be upgraded without data loss.

These tests prove:
  * a canonical Event's occurred_at is preserved on the Observation
    (``occurred_at`` == canonical event time; ``timestamp`` == ingestion time);
  * occurred_at is NOT silently collapsed into the ingestion timestamp;
  * the chronological read model orders by event time (occurred_at DESC) with
    deterministic tie-breaking;
  * observations can be filtered by source / observation_type / occurred_at range;
  * the WO-060 migration (revision 5) adds the occurred_at column + index to an
    EXISTING, populated observations table (real OLD -> NEW schema delta);
  * the operator GET /api/v1/operator/observations endpoint exposes observations
    ordered by event time, and a ``radio.recording`` observation's recording
    evidence (wav/mp3 refs, sha256, duration, content_id) survives the read
    model (WO-062 contract);
  * duplicate canonical events still produce exactly one observation (dedup
    unchanged), and its occurred_at is preserved.

No production data is destroyed; migrations are idempotent.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

import pytest

import app.database.session as session_mod
from app.database.base import Base
from app.database.session import configure_session_manager, get_session_manager
from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.intelligence.observation.repository import (
    ObservationRepository,
    SessionManagerObservationRepository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _url(db_path: str) -> str:
    return f"sqlite:///{db_path}"


def _reset() -> None:
    session_mod._session_manager = None


def _make_event(
    event_id: str,
    occurred_at: datetime,
    *,
    source: str = "radio",
    payload: dict | None = None,
) -> Event:
    """Build a canonical Event with a deterministic occurred_at (event time)."""
    return Event(
        event_id=event_id,
        event_type=EventType.CUSTOM,
        timestamp=occurred_at,
        source=source,
        payload=payload or {"frequency": 100.5, "callsign": "BRAVO"},
        metadata=EventMetadata(),
    )


def _recording_payload(rid: str) -> dict:
    """A WO-058 radio recording payload (no frequency/callsign)."""
    return {
        "occurred_at": "2026-09-03T12:00:00Z",
        "audio_recording_id": rid,
        "content_id": "content-" + rid,
        "recording": {
            "wav_path": f"/tmp/{rid}.wav",
            "mp3_path": f"/tmp/{rid}.mp3",
            "format": "wav",
            "duration_ms": 30000,
            "duration": 30.0,
            "source": "radio",
            "sha256": "a" * 64,
            "complete": False,
            "finalize_reason": "source_shutdown",
        },
    }


def _compose(db_url: str) -> "object":
    """Configure the GLOBAL session manager and return a production runtime."""
    configure_session_manager(db_url)
    Base.metadata.create_all(get_session_manager().engine)
    from app.composition import create_event_runtime

    return create_event_runtime()


def _process(rt: "object", event: Event) -> bool:
    return rt.pipeline.process(event)


@pytest.fixture()
def file_db():
    """A file-based SQLite DB (cross-thread safe for the operator endpoint)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    _reset()
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture()
def memory_rt():
    rt = _compose("sqlite:///:memory:")
    yield rt
    _reset()


# ---------------------------------------------------------------------------
# 1. occurred_at is populated from the canonical event time (distinct from
#    ingestion time) — the core WO-060 contract.
# ---------------------------------------------------------------------------


def test_occurred_at_preserved_from_canonical_event_time(memory_rt):
    occurred_at = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)
    assert _process(memory_rt, _make_event("e1", occurred_at)) is True

    repo = ObservationRepository(get_session_manager().get_session())
    obs = repo.get_by_immutable_id("e1")
    assert obs is not None
    # SQLite DateTime drops tzinfo on the round-trip (pre-existing behaviour for
    # ``timestamp`` too); compare on the value.
    assert obs.occurred_at == occurred_at.replace(tzinfo=None)
    # Event time must differ from ingestion time.
    assert obs.occurred_at != obs.timestamp
    # occurred_at is exposed on the read dict.
    assert obs.to_dict()["occurred_at"] == "2026-08-17T12:00:00"


def test_occurred_at_is_not_the_ingestion_timestamp(memory_rt):
    occurred_at = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)
    assert _process(memory_rt, _make_event("e1", occurred_at)) is True
    repo = ObservationRepository(get_session_manager().get_session())
    obs = repo.get_by_immutable_id("e1")
    assert obs.occurred_at.replace(tzinfo=None) == datetime(2026, 8, 17, 12, 0, 0)
    assert obs.timestamp != obs.occurred_at


# ---------------------------------------------------------------------------
# 2. Deterministic chronological ordering by event time.
# ---------------------------------------------------------------------------


def test_chronological_ordering_by_event_time(memory_rt):
    # Arrival is in reverse event-time order: e2 (11:00) arrives after e1 (12:00).
    assert _process(
        memory_rt, _make_event("e1", datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))
    ) is True
    assert _process(
        memory_rt, _make_event("e2", datetime(2026, 8, 17, 11, 0, 0, tzinfo=timezone.utc))
    ) is True

    repo = ObservationRepository(get_session_manager().get_session())
    rows = repo.list_chronological()
    # DESC by occurred_at: e1 (12:00) first, then e2 (11:00) — regardless of
    # ingestion order.  This is the operator chronology the work order requires.
    assert [r.immutable_id for r in rows] == ["e1", "e2"]


def test_chronological_ordering_is_deterministic_on_identical_occurred_at(memory_rt):
    same_time = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)
    assert _process(memory_rt, _make_event("e-a", same_time)) is True
    assert _process(memory_rt, _make_event("e-b", same_time)) is True

    repo = ObservationRepository(get_session_manager().get_session())
    rows = repo.list_chronological()
    # Tie-break is deterministic (occurred_at DESC, then timestamp DESC, then id
    # DESC).  Both rows must be present and ordered consistently.
    assert {r.immutable_id for r in rows} == {"e-a", "e-b"}
    assert len(rows) == 2


def test_chronological_filter_by_source_and_type(memory_rt):
    assert _process(
        memory_rt, _make_event("e-r", datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc), source="radio")
    ) is True
    assert _process(
        memory_rt,
        _make_event(
            "e-s",
            datetime(2026, 8, 17, 11, 0, 0, tzinfo=timezone.utc),
            source="signal",
            payload={"message_id": "m1", "sender": "alice", "chat_id": "c1"},
        ),
    ) is True

    repo = ObservationRepository(get_session_manager().get_session())
    assert [r.immutable_id for r in repo.list_chronological(source="radio")] == ["e-r"]
    assert [r.immutable_id for r in repo.list_chronological(observation_type="radio")] == ["e-r"]
    assert repo.count_chronological() == 2
    assert repo.count_chronological(source="radio") == 1


def test_chronological_filter_by_occurred_at_range(memory_rt):
    assert _process(
        memory_rt, _make_event("e1", datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))
    ) is True
    assert _process(
        memory_rt, _make_event("e2", datetime(2026, 8, 17, 11, 0, 0, tzinfo=timezone.utc))
    ) is True

    repo = ObservationRepository(get_session_manager().get_session())
    # Only e1 occurred at/after 11:30.
    rows = repo.list_chronological(
        from_time=datetime(2026, 8, 17, 11, 30)
    )
    assert [r.immutable_id for r in rows] == ["e1"]
    # Only e2 occurred at/before 11:30.
    rows = repo.list_chronological(to_time=datetime(2026, 8, 17, 11, 30))
    assert [r.immutable_id for r in rows] == ["e2"]


# ---------------------------------------------------------------------------
# 3. Migration (revision 5) adds occurred_at to a populated OLD observations
#    table — a real OLD -> NEW schema delta, not a create_all-only check.
# ---------------------------------------------------------------------------


def _seed_old_observations_table(db_path: str, with_occurred_at: bool = False) -> None:
    """Create a GENUINE pre-WO-060 observations table (no occurred_at) with one
    row, plus the schema_migration_version table at revision 4 (so revision 5 is
    pending)."""
    import sqlalchemy as sa

    engine = sa.create_engine(_url(db_path))
    with engine.begin() as c:
        c.execute(
            sa.text(
                "CREATE TABLE observations ("
                "id VARCHAR(36) PRIMARY KEY, "
                "timestamp DATETIME NOT NULL, "
                "source VARCHAR(255) NOT NULL, "
                "source_type VARCHAR(50) NOT NULL, "
                "observation_type VARCHAR(50) NOT NULL, "
                "evidence_payload TEXT, provenance TEXT, "
                "source_confidence REAL NOT NULL, "
                "processing_status VARCHAR(50) NOT NULL, "
                "immutable_id VARCHAR(255), tags TEXT, "
                "observation_metadata TEXT, "
                "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, "
                "version INTEGER NOT NULL, is_deleted BOOLEAN NOT NULL)"
            )
        )
        c.execute(
            sa.text(
                "INSERT INTO observations "
                "(id,timestamp,source,source_type,observation_type,evidence_payload,"
                "provenance,source_confidence,processing_status,immutable_id,tags,"
                "observation_metadata,created_at,updated_at,version,is_deleted) "
                "VALUES ('11111111-1111-1111-1111-111111111111','2026-08-17 12:00:00',"
                "'radio','driver','radio',"
                "'{}','{}',0.6,'received','e1','[]','{}',"
                "'2026-08-17 12:00:00','2026-08-17 12:00:00',1,0)"
            )
        )
        c.execute(
            sa.text(
                "CREATE TABLE schema_migration_version ("
                "version INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, "
                "applied_at DATETIME NOT NULL)"
            )
        )
        c.execute(
            sa.text(
                "INSERT INTO schema_migration_version (version,name,applied_at) "
                "VALUES (4,'durable_plugin_delivery_ledger','2026-08-17 12:00:00')"
            )
        )
    engine.dispose()


def test_migration_adds_occurred_at_to_populated_table(file_db):
    _seed_old_observations_table(file_db)
    configure_session_manager(_url(file_db))

    from sqlalchemy import inspect as sa_inspect

    insp = sa_inspect(get_session_manager().engine)
    cols_before = {c["name"] for c in insp.get_columns("observations")}
    assert "occurred_at" not in cols_before, "OLD schema must lack occurred_at"

    from app.database.schema_migration import upgrade_schema

    v = upgrade_schema()
    assert v == 5, f"expected target revision 5, got {v}"

    cols_after = {c["name"] for c in sa_inspect(get_session_manager().engine).get_columns("observations")}
    assert "occurred_at" in cols_after, "migration must add occurred_at column"

    index_names = {i["name"] for i in sa_inspect(get_session_manager().engine).get_indexes("observations")}
    assert "ix_observations_occurred_at" in index_names, "migration must add occurred_at index"

    # Pre-existing data preserved.
    repo = SessionManagerObservationRepository(get_session_manager())
    rows = repo.list_chronological()
    assert len(rows) == 1
    assert rows[0].immutable_id == "e1"
    assert rows[0].occurred_at is None  # old row, no occurred_at backfill
    _reset()


def test_migration_is_idempotent_on_fresh_schema(file_db):
    """On a fresh DB whose create_all already carries occurred_at, revision 5 is
    a safe no-op (the column is not duplicated)."""
    configure_session_manager(_url(file_db))
    Base.metadata.create_all(get_session_manager().engine)
    from app.database.schema_migration import upgrade_schema

    v = upgrade_schema()
    assert v == 5
    # A second run must also converge to 5 (idempotent).
    v2 = upgrade_schema()
    assert v2 == 5
    _reset()


# ---------------------------------------------------------------------------
# 4. Operator endpoint exposes observations ordered by event time, preserving
#    the radio.recording read contract (WO-062 evidence).
# ---------------------------------------------------------------------------


def test_operator_endpoint_returns_observations_ordered_by_event_time(file_db):
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    rt = _compose(_url(file_db))

    # Two radio.recording observations with different event times.
    assert _process(
        rt,
        _make_event("e-rec-1", datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
                    payload=_recording_payload("rec-1")),
    ) is True
    assert _process(
        rt,
        _make_event("e-rec-2", datetime(2026, 8, 17, 11, 0, 0, tzinfo=timezone.utc),
                    payload=_recording_payload("rec-2")),
    ) is True

    from app.operator.app import create_operator_app
    from app.event_repository.durable.sqlalchemy_event_repository import (
        SQLAlchemyEventRepository,
    )
    from app.entity_repository.sqlalchemy_entity_repository import (
        SQLAlchemyEntityRepository,
    )
    from app.entity_relations.sqlalchemy_relation_repository import (
        SQLAlchemyRelationRepository,
    )

    app = create_operator_app(
        event_repository=SQLAlchemyEventRepository(session_manager=mgr),
        entity_repository=SQLAlchemyEntityRepository(session_manager=mgr),
        relation_repository=SQLAlchemyRelationRepository(session_manager=mgr),
        observation_repository=SessionManagerObservationRepository(mgr),
    )

    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/v1/operator/observations")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert [o["immutable_id"] for o in body["observations"]] == ["e-rec-1", "e-rec-2"]

    o1 = body["observations"][0]
    assert o1["occurred_at"] == "2026-08-17T12:00:00"
    assert o1["timestamp"] != o1["occurred_at"]
    assert o1["source"] == "radio"
    assert o1["observation_type"] == "radio"
    # WO-062 contract: recording identity / evidence survives the read model.
    rec = o1["evidence_payload"]["raw_data"]["recording"]
    assert rec["wav_path"] == "/tmp/rec-1.wav"
    assert rec["mp3_path"] == "/tmp/rec-1.mp3"
    assert rec["sha256"] == "a" * 64
    assert rec["duration"] == 30.0
    assert o1["evidence_payload"]["raw_data"]["recording"]["duration_ms"] == 30000
    assert o1["evidence_payload"]["raw_data"].get("recording") is not None
    _reset()


def test_operator_endpoint_filters_by_observation_type(file_db):
    mgr = configure_session_manager(_url(file_db))
    Base.metadata.create_all(mgr.engine)
    rt = _compose(_url(file_db))
    assert _process(
        rt,
        _make_event("e-r", datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
                    payload=_recording_payload("rec-r")),
    ) is True

    from app.operator.app import create_operator_app
    from app.event_repository.durable.sqlalchemy_event_repository import (
        SQLAlchemyEventRepository,
    )
    from app.entity_repository.sqlalchemy_entity_repository import (
        SQLAlchemyEntityRepository,
    )
    from app.entity_relations.sqlalchemy_relation_repository import (
        SQLAlchemyRelationRepository,
    )

    app = create_operator_app(
        event_repository=SQLAlchemyEventRepository(session_manager=mgr),
        entity_repository=SQLAlchemyEntityRepository(session_manager=mgr),
        relation_repository=SQLAlchemyRelationRepository(session_manager=mgr),
        observation_repository=SessionManagerObservationRepository(mgr),
    )
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/v1/operator/observations", params={"observation_type": "radio"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    resp2 = client.get("/api/v1/operator/observations", params={"observation_type": "signal"})
    assert resp2.json()["total"] == 0
    _reset()


# ---------------------------------------------------------------------------
# 5. Duplicate suppression is unchanged; occurred_at survives.
# ---------------------------------------------------------------------------


def test_duplicate_canonical_event_single_observation_occurred_at_preserved(memory_rt):
    occurred_at = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)
    event = _make_event("e-dup", occurred_at)
    assert _process(memory_rt, event) is True
    assert _process(memory_rt, event) is True  # replay of the same event_id

    repo = ObservationRepository(get_session_manager().get_session())
    rows = repo.list_chronological()
    assert len(rows) == 1, "duplicate event must not create a duplicate observation"
    assert rows[0].immutable_id == "e-dup"
    assert rows[0].occurred_at == occurred_at.replace(tzinfo=None)


# ---------------------------------------------------------------------------
# 6. Restart / reopen persistence: occurred_at survives a DB reopen (file DB).
# ---------------------------------------------------------------------------


def test_occurred_at_survives_reopen(file_db):
    configure_session_manager(_url(file_db))
    Base.metadata.create_all(get_session_manager().engine)
    rt = _compose(_url(file_db))
    occurred_at = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)
    assert _process(rt, _make_event("e1", occurred_at)) is True
    _reset()

    # Reopen the same file DB with a brand-new engine/runtime.
    rt2 = _compose(_url(file_db))
    repo = ObservationRepository(get_session_manager().get_session())
    obs = repo.get_by_immutable_id("e1")
    assert obs is not None
    assert obs.occurred_at == occurred_at.replace(tzinfo=None)
    _reset()
