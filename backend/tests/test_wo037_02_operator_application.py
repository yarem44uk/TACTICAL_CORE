"""WO-037-02 tests: Operator Application Foundation.

Exercises the real FastAPI operator application against the actual
authoritative repositories backed by a file-based SQLite database.

NOTE on SQLite threading: FastAPI's TestClient executes requests in a worker
thread, while the in-memory (``:memory:``) SQLite StaticPool connection is
bound to the creating thread. To exercise the HTTP layer for real, these tests
use a file-based SQLite database (``QueuePool`` + ``check_same_thread=False``),
which is safely shareable across the TestClient worker thread. Pure-repository
behaviour (pagination/filters) is already covered by WO-037-01 tests against an
in-memory DB and is not re-tested here at the repository seam.

Coverage:
A. application factory starts; routes are registered; operator process does
   not require backend/main.py
B. events: list, cursor pagination, source/event_type/time filters, detail,
   missing -> 404, malformed cursor -> 400, invalid limit -> 400
C. entities: list, detail, missing -> 404
D. relations: entity relations endpoint, missing entity -> 404
E. health: authoritative metrics; unavailable metric represented honestly
F. read-only guarantee (no state mutation)
G. HTTP methods: unsupported mutation methods -> 405
H. error handling: 400 / 404 / 503 / 500
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.database.session import DatabaseSessionManager
from app.entity_relations.sqlalchemy_relation_repository import (
    SQLAlchemyRelationRepository,
)
from app.entity_repository.sqlalchemy_entity_repository import (
    SQLAlchemyEntityRepository,
)
from app.event.event import Event
from app.event.event_types import EventType
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)
from app.operator.app import create_operator_app


@pytest.fixture()
def db_path() -> str:
    """A fresh temp file path for a file-based SQLite DB per test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture()
def session_manager(db_path: str) -> DatabaseSessionManager:
    """A fresh file-based SQLite session manager (thread-safe for TestClient)."""
    manager = DatabaseSessionManager(database_url=f"sqlite:///{db_path}", echo=False)
    manager.initialize()
    yield manager
    manager.close()


@pytest.fixture()
def repos(session_manager: DatabaseSessionManager):
    """Construct authoritative repositories bound to the test DB."""
    event_repo = SQLAlchemyEventRepository(session_manager=session_manager)
    event_repo.initialize()
    entity_repo = SQLAlchemyEntityRepository(session_manager=session_manager)
    entity_repo.initialize()
    relation_repo = SQLAlchemyRelationRepository(session_manager=session_manager)
    relation_repo.initialize()
    return event_repo, entity_repo, relation_repo


@pytest.fixture()
def client(repos):
    """A TestClient against the real operator app with the test repositories."""
    event_repo, entity_repo, relation_repo = repos
    app = create_operator_app(
        event_repository=event_repo,
        entity_repository=entity_repo,
        relation_repository=relation_repo,
    )
    return TestClient(app)


def make_event(
    *,
    event_id: str,
    event_type: EventType = EventType.CUSTOM,
    source: str = "test-source",
    timestamp: datetime,
) -> Event:
    """Build a canonical domain Event with deterministic identity/time."""
    return Event(
        event_id=event_id,
        event_type=event_type,
        timestamp=timestamp,
        source=source,
        payload={"k": "v"},
    )


def seed_events(event_repo: SQLAlchemyEventRepository, n: int = 25) -> None:
    """Persist n events with increasing timestamps and deterministic ids."""
    base = datetime(2026, 8, 1)
    for i in range(n):
        source = "alpha" if i % 2 == 0 else "beta"
        etype = EventType.ENTITY_CREATED if i % 3 == 0 else EventType.CUSTOM
        ts = base.replace(hour=(i % 24), minute=(i % 60))
        ev = make_event(
            event_id=f"evt-{i:04d}",
            event_type=etype,
            source=source,
            timestamp=ts,
        )
        event_repo.save(ev)


# -- Application -------------------------------------------------------------


def test_application_factory_creates_app(repos) -> None:
    event_repo, entity_repo, relation_repo = repos
    app = create_operator_app(
        event_repository=event_repo,
        entity_repository=entity_repo,
        relation_repository=relation_repo,
    )
    assert app.title == "Tactical Core Operator API"
    assert app.state.operator_service is not None


def test_operator_process_does_not_require_main(repos) -> None:
    """The operator package must not import backend.main / the durable engine.

    Verified statically (not via runtime ``sys.modules``, which the full test
    suite pollutes by importing other modules first): the operator source files
    must contain no import of ``backend.main`` / the durable engine components.
    """
    import os
    import re

    operator_dir = os.path.join(
        os.path.dirname(__file__), "..", "app", "operator"
    )
    forbidden = re.compile(
        r"^\s*(from|import)\s+.*(backend\.main|app\.bootstrap"
        r"|EventPipeline|DurableDeliveryDispatcher|ReconstructionService)",
        re.MULTILINE,
    )
    for fname in os.listdir(operator_dir):
        if not fname.endswith(".py"):
            continue
        with open(os.path.join(operator_dir, fname), encoding="utf-8") as fh:
            source = fh.read()
        # Only flag actual import statements, not docstring prose.
        code_lines = [
            line
            for line in source.splitlines()
            if not line.strip().startswith(('"""', "'"))
        ]
        for line in code_lines:
            # Skip docstring/comment references (they are explanatory).
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith(("'''", '"""')):
                continue
            assert not forbidden.match(line), (
                f"operator file {fname} references forbidden durable-engine "
                f"import: {line!r}"
            )


def test_api_prefix_registered(client) -> None:
    r = client.get("/api/v1/operator/health")
    assert r.status_code == 200
    # Anything outside the operator prefix should 404 (no foreign routes).
    assert client.get("/api/v1/other").status_code == 404


# -- Events ------------------------------------------------------------------


def test_event_list(client, repos) -> None:
    event_repo, _, _ = repos
    seed_events(event_repo, 25)
    r = client.get("/api/v1/operator/events", params={"limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert len(body["events"]) == 10
    assert body["next_cursor"] == 10
    assert body["events"][0]["event_id"] == "evt-0000"


def test_event_cursor_pagination(client, repos) -> None:
    event_repo, _, _ = repos
    seed_events(event_repo, 25)
    r1 = client.get("/api/v1/operator/events", params={"limit": 10})
    assert r1.status_code == 200
    cursor = r1.json()["next_cursor"]
    r2 = client.get(
        "/api/v1/operator/events", params={"limit": 10, "cursor": cursor}
    )
    assert r2.status_code == 200
    body = r2.json()
    assert [e["event_id"] for e in body["events"]] == [
        f"evt-{i:04d}" for i in range(10, 20)
    ]
    r3 = client.get(
        "/api/v1/operator/events",
        params={"limit": 10, "cursor": body["next_cursor"]},
    )
    assert [e["event_id"] for e in r3.json()["events"]] == [
        f"evt-{i:04d}" for i in range(20, 25)
    ]
    assert r3.json()["next_cursor"] is None


def test_event_source_filter(client, repos) -> None:
    event_repo, _, _ = repos
    seed_events(event_repo, 25)
    r = client.get("/api/v1/operator/events", params={"source": "alpha"})
    assert r.status_code == 200
    body = r.json()
    assert body["events"] and all(e["source"] == "alpha" for e in body["events"])
    assert len(body["events"]) == 13


def test_event_type_filter(client, repos) -> None:
    event_repo, _, _ = repos
    seed_events(event_repo, 25)
    r = client.get(
        "/api/v1/operator/events",
        params={"event_type": str(EventType.ENTITY_CREATED)},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["events"]
    assert all(
        e["event_type"] == str(EventType.ENTITY_CREATED) for e in body["events"]
    )


def test_event_time_filters(client, repos) -> None:
    event_repo, _, _ = repos
    seed_events(event_repo, 25)
    r = client.get(
        "/api/v1/operator/events",
        params={"from_time": "2026-08-01T04:00:00", "to_time": "2026-08-01T08:00:00"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["events"]
    for e in body["events"]:
        ts = datetime.fromisoformat(e["timestamp"])
        assert datetime(2026, 8, 1, 4) <= ts < datetime(2026, 8, 1, 8)


def test_event_detail(client, repos) -> None:
    event_repo, _, _ = repos
    seed_events(event_repo, 5)
    r = client.get("/api/v1/operator/events/evt-0002")
    assert r.status_code == 200
    body = r.json()
    assert body["event_id"] == "evt-0002"
    assert body["seq"] == 3


def test_event_detail_not_found(client) -> None:
    r = client.get("/api/v1/operator/events/evt-9999")
    assert r.status_code == 404
    assert r.json()["error_type"] == "NotFoundError"


def test_event_malformed_cursor_400(client) -> None:
    r = client.get("/api/v1/operator/events", params={"cursor": "not-an-int"})
    assert r.status_code == 400


def test_event_invalid_limit_400(client) -> None:
    r = client.get("/api/v1/operator/events", params={"limit": 0})
    assert r.status_code == 400


# -- Entities ----------------------------------------------------------------


def test_entity_list(client, repos) -> None:
    _, entity_repo, _ = repos
    entity_repo.save(
        {
            "entity_id": "ent-1",
            "entity_type": "person",
            "status": "UNKNOWN",
            "attributes": {"name": "x"},
        }
    )
    r = client.get("/api/v1/operator/entities")
    assert r.status_code == 200
    body = r.json()
    assert len(body["entities"]) == 1
    assert body["entities"][0]["entity_id"] == "ent-1"


def test_entity_detail(client, repos) -> None:
    _, entity_repo, _ = repos
    entity_repo.save({"entity_id": "ent-1", "entity_type": "person"})
    r = client.get("/api/v1/operator/entities/ent-1")
    assert r.status_code == 200
    assert r.json()["entity"]["entity_id"] == "ent-1"


def test_entity_detail_not_found(client) -> None:
    r = client.get("/api/v1/operator/entities/ent-missing")
    assert r.status_code == 404


# -- Relations ---------------------------------------------------------------


def test_entity_relations(client, repos) -> None:
    _, entity_repo, relation_repo = repos
    entity_repo.save({"entity_id": "ent-a", "entity_type": "person"})
    relation_repo.save(
        {
            "relation_id": "rel-1",
            "source_entity_id": "ent-a",
            "target_entity_id": "ent-b",
            "relation_type": "associated_with",
        }
    )
    r = client.get("/api/v1/operator/entities/ent-a/relations")
    assert r.status_code == 200
    body = r.json()
    assert body["entity_id"] == "ent-a"
    assert len(body["relations"]) == 1
    assert body["relations"][0]["relation_id"] == "rel-1"


def test_entity_relations_missing_entity(client) -> None:
    r = client.get("/api/v1/operator/entities/ent-missing/relations")
    assert r.status_code == 404


# -- Health ------------------------------------------------------------------


def test_health_reports_authoritative_metrics(client, repos) -> None:
    event_repo, entity_repo, _ = repos
    seed_events(event_repo, 3)
    entity_repo.save({"entity_id": "ent-1", "entity_type": "person"})
    r = client.get("/api/v1/operator/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["durable_events"] == 3
    assert body["durable_entities"] == 1
    # last_ingestion is not persisted by the authoritative system.
    assert body["last_ingestion"] == "unavailable"


# -- Read-only guarantee ------------------------------------------------------


def test_operator_requests_do_not_mutate_state(client, repos) -> None:
    event_repo, entity_repo, relation_repo = repos
    seed_events(event_repo, 5)
    entity_repo.save({"entity_id": "ent-a", "entity_type": "person"})
    relation_repo.save(
        {
            "relation_id": "rel-1",
            "source_entity_id": "ent-a",
            "target_entity_id": "ent-b",
            "relation_type": "associated_with",
        }
    )
    events_before = event_repo.count()
    entities_before = entity_repo.count()

    client.get("/api/v1/operator/events", params={"limit": 3})
    client.get("/api/v1/operator/events/evt-0001")
    client.get("/api/v1/operator/entities")
    client.get("/api/v1/operator/entities/ent-a/relations")
    client.get("/api/v1/operator/health")

    assert event_repo.count() == events_before
    assert entity_repo.count() == entities_before
    # Relations untouched.
    assert len(relation_repo.list_for_entity("ent-a")) == 1


# -- HTTP methods -------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/v1/operator/events"),
        ("put", "/api/v1/operator/events/e1"),
        ("patch", "/api/v1/operator/events/e1"),
        ("delete", "/api/v1/operator/events/e1"),
        ("post", "/api/v1/operator/entities"),
        ("post", "/api/v1/operator/health"),
    ],
)
def test_mutation_methods_return_405(client, method: str, path: str) -> None:
    r = getattr(client, method)(path)
    assert r.status_code == 405


# -- Error handling (503 / 500) ----------------------------------------------


def test_503_when_read_dependency_unavailable(db_path: str) -> None:
    """A repository that fails reads must surface as 503 (not leak internals)."""

    class BrokenEventRepo(SQLAlchemyEventRepository):
        def query_events(self, **kwargs):
            raise RuntimeError("backend exploded")

    class BrokenEntityRepo(SQLAlchemyEntityRepository):
        def list_all(self, **kwargs):
            raise RuntimeError("backend exploded")

    class BrokenRelationRepo(SQLAlchemyRelationRepository):
        def list_for_entity(self, entity_id, status=None):
            raise RuntimeError("backend exploded")

    app = create_operator_app(
        event_repository=BrokenEventRepo(),  # type: ignore[arg-type]
        entity_repository=BrokenEntityRepo(),  # type: ignore[arg-type]
        relation_repository=BrokenRelationRepo(),  # type: ignore[arg-type]
    )
    c = TestClient(app)
    r = c.get("/api/v1/operator/events")
    assert r.status_code == 503
    body = r.json()
    # Must not leak the underlying exception text / internals.
    assert "backend exploded" not in r.text
    assert body["error_type"] == "ReadDependencyUnavailableError"


def test_500_on_unexpected_operator_error(db_path: str) -> None:
    """An unexpected operator-layer error maps to 500 without leaking internals."""

    class ExplodingService:
        def health(self):
            raise ValueError("internal secret detail")

    app = create_operator_app(
        event_repository=SQLAlchemyEventRepository(),
        entity_repository=SQLAlchemyEntityRepository(),
        relation_repository=SQLAlchemyRelationRepository(),
    )
    # Inject a service that raises an unexpected (non-OperatorError) failure.
    app.state.operator_service = ExplodingService()  # type: ignore[assignment]
    # raise_server_exceptions=False so the 500 handler's response is returned
    # (instead of TestClient re-raising the server-side exception).
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/api/v1/operator/health")
    assert r.status_code == 500
    assert "internal secret detail" not in r.text
    assert r.json()["error_type"] == "InternalServerError"
