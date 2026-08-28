"""WO-037-04 tests: SSE Best-Effort Realtime stream.

Exercises the operator FastAPI ``GET /api/v1/operator/events/stream`` SSE
endpoint (ADR-011 §12):

  * endpoint exists and returns ``text/event-stream``;
  * deterministic SSE framing with ``id`` = durable seq;
  * bounded initial snapshot on fresh connect;
  * Last-Event-ID resume from the authoritative durable seq;
  * new events persisted after a cursor are delivered on resume;
  * ordering is based on the authoritative monotonic ``seq``;
  * reconnect / resume never creates durable SSE state;
  * no mutation methods (POST/PUT/PATCH/DELETE -> 405);
  * event/entity counts are unchanged after SSE usage (read-only);
  * malformed Last-Event-ID / invalid limit / invalid stream_ticks -> 400;
  * read-dependency unavailable -> 503 (before streaming).

The SSE endpoint is an intentionally infinite realtime tail. Tests request the
``stream_ticks=0`` bound so each stream is finite (initial snapshot + one tail
poll + keepalive) and fully deterministic — no timing sleeps, no flakiness.

Same file-based SQLite harness as WO-037-02/03 (thread-safe). SSE streaming is
consumed with ``httpx.AsyncClient`` over ``ASGITransport`` because the installed
Starlette ``TestClient`` cannot stream SSE responses in this environment.
"""

from __future__ import annotations

import json
import os
import tempfile

import httpx
import pytest

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
from app.operator.router import _sse_frame

STREAM_URL = "/api/v1/operator/events/stream"


def _make_event(event_id: str, source: str = "sse-test") -> Event:
    return Event(
        event_id=event_id,
        entity_id=f"entity-{event_id}",
        event_type=EventType.CUSTOM,
        source=source,
        payload={"note": event_id},
    )


def _parse_frames(body: bytes) -> list:
    """Parse an SSE body into a list of (event_id, data_dict) frames.

    Keepalive comment frames (``: ...``) and blank separators are skipped.
    """
    frames: list = []
    for block in body.decode("utf-8").split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        event_id = None
        data = None
        for line in block.split("\n"):
            if line.startswith("id:"):
                event_id = int(line.split(":", 1)[1].strip())
            elif line.startswith("data:"):
                raw = line.split(":", 1)[1].strip()
                if raw:
                    data = json.loads(raw)
        if data is not None:
            frames.append((event_id, data))
    return frames


@pytest.fixture()
def db_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture()
def session_manager(db_path: str) -> DatabaseSessionManager:
    manager = DatabaseSessionManager(database_url=f"sqlite:///{db_path}", echo=False)
    manager.initialize()
    yield manager
    manager.close()


@pytest.fixture()
def repos(session_manager: DatabaseSessionManager):
    event_repo = SQLAlchemyEventRepository(session_manager=session_manager)
    event_repo.initialize()
    entity_repo = SQLAlchemyEntityRepository(session_manager=session_manager)
    entity_repo.initialize()
    relation_repo = SQLAlchemyRelationRepository(session_manager=session_manager)
    relation_repo.initialize()
    return event_repo, entity_repo, relation_repo


@pytest.fixture()
def event_repo(repos) -> SQLAlchemyEventRepository:
    return repos[0]


@pytest.fixture()
def app(repos):
    event_repo, entity_repo, relation_repo = repos
    return create_operator_app(
        event_repository=event_repo,
        entity_repository=entity_repo,
        relation_repository=relation_repo,
    )


async def _get_sse(app, url: str, headers=None) -> tuple:
    """GET an SSE URL over ASGITransport and return (status_code, frames).

    Uses ``stream_ticks=0`` so the stream is finite and fully drained.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        async with client.stream("GET", url, headers=headers) as response:
            body = b"".join([chunk async for chunk in response.aiter_bytes()])
            return response.status_code, _parse_frames(body)


# -- application / route -----------------------------------------------------


@pytest.mark.asyncio
async def test_sse_endpoint_returns_stream_content_type(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        async with client.stream(
            "GET", f"{STREAM_URL}?stream_ticks=0"
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")


# -- initial snapshot --------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_initial_snapshot_delivers_seeded_events_in_seq_order(
    app, event_repo: SQLAlchemyEventRepository
) -> None:
    for i in range(1, 4):
        event_repo.save(_make_event(f"e{i}"))
    status, frames = await _get_sse(app, f"{STREAM_URL}?stream_ticks=0")
    assert status == 200
    assert [f[0] for f in frames] == [1, 2, 3]
    assert [f[1]["event"]["event_id"] for f in frames] == ["e1", "e2", "e3"]


@pytest.mark.asyncio
async def test_sse_snapshot_respects_limit(
    app, event_repo: SQLAlchemyEventRepository
) -> None:
    for i in range(1, 6):
        event_repo.save(_make_event(f"e{i}"))
    status, frames = await _get_sse(app, f"{STREAM_URL}?limit=2&stream_ticks=0")
    assert status == 200
    assert [f[0] for f in frames] == [4, 5]
    assert [f[1]["event"]["event_id"] for f in frames] == ["e4", "e5"]


@pytest.mark.asyncio
async def test_sse_empty_log_snapshot_is_empty(app) -> None:
    status, frames = await _get_sse(app, f"{STREAM_URL}?stream_ticks=0")
    assert status == 200
    assert frames == []


# -- Last-Event-ID resume ----------------------------------------------------


@pytest.mark.asyncio
async def test_sse_last_event_id_resumes_after_cursor(
    app, event_repo: SQLAlchemyEventRepository
) -> None:
    for i in range(1, 6):
        event_repo.save(_make_event(f"e{i}"))
    status, frames = await _get_sse(
        app, f"{STREAM_URL}?stream_ticks=0", headers={"Last-Event-ID": "3"}
    )
    assert status == 200
    assert [f[0] for f in frames] == [4, 5]
    assert [f[1]["event"]["event_id"] for f in frames] == ["e4", "e5"]


@pytest.mark.asyncio
async def test_sse_resume_delivers_new_event_persisted_after_cursor(
    app, event_repo: SQLAlchemyEventRepository
) -> None:
    for i in range(1, 4):
        event_repo.save(_make_event(f"e{i}"))
    # A new event is durably persisted after the client's cursor (seq 3).
    event_repo.save(_make_event("new-after-cursor"))
    status, frames = await _get_sse(
        app, f"{STREAM_URL}?stream_ticks=0", headers={"Last-Event-ID": "3"}
    )
    assert status == 200
    assert [f[0] for f in frames] == [4]
    assert frames[0][1]["event"]["event_id"] == "new-after-cursor"


# -- ordering ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_ordering_uses_authoritative_seq(
    app, event_repo: SQLAlchemyEventRepository
) -> None:
    event_repo.save(_make_event("first"))
    event_repo.save(_make_event("second"))
    event_repo.save(_make_event("third"))
    status, frames = await _get_sse(app, f"{STREAM_URL}?stream_ticks=0")
    assert status == 200
    assert [f[1]["event"]["event_id"] for f in frames] == [
        "first",
        "second",
        "third",
    ]
    assert [f[0] for f in frames] == [1, 2, 3]


# -- SSE framing helper ------------------------------------------------------


def test_sse_frame_formatting() -> None:
    frame = _sse_frame(7, {"event_id": "x", "seq": 7})
    assert frame.startswith("id: 7\n")
    assert "data: " in frame
    assert frame.endswith("\n\n")


# -- read-only ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_usage_does_not_mutate_authoritative_state(
    app, event_repo: SQLAlchemyEventRepository
) -> None:
    event_repo.save(_make_event("e1"))
    before_events = event_repo.count()
    await _get_sse(app, f"{STREAM_URL}?stream_ticks=0")
    await _get_sse(
        app, f"{STREAM_URL}?stream_ticks=0", headers={"Last-Event-ID": "1"}
    )
    assert event_repo.count() == before_events


# -- HTTP method enforcement -------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
async def test_sse_mutation_methods_return_405(app, method: str) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        response = await getattr(client, method)(STREAM_URL)
    assert response.status_code == 405


# -- error contract ----------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_malformed_last_event_id_returns_400(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        async with client.stream(
            "GET", STREAM_URL, headers={"Last-Event-ID": "not-an-int"}
        ) as response:
            assert response.status_code == 400


@pytest.mark.asyncio
async def test_sse_invalid_limit_returns_400(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        response = await client.get(f"{STREAM_URL}?limit=0")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_sse_invalid_stream_ticks_returns_400(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        response = await client.get(f"{STREAM_URL}?stream_ticks=-1")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_sse_read_dependency_unavailable_returns_503() -> None:
    """A failing event repository -> pre-flight availability check -> 503."""

    class _FailingEventRepo:
        def max_seq(self) -> int:
            raise RuntimeError("db down")

    app = create_operator_app(
        event_repository=_FailingEventRepo(),  # type: ignore[arg-type]
        entity_repository=SQLAlchemyEntityRepository(
            session_manager=DatabaseSessionManager("sqlite:///:memory:")
        ),
        relation_repository=SQLAlchemyRelationRepository(
            session_manager=DatabaseSessionManager("sqlite:///:memory:")
        ),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        async with client.stream("GET", STREAM_URL) as response:
            assert response.status_code == 503


# -- service layer primitives ------------------------------------------------


def test_service_events_after_seq_ordering(
    event_repo: SQLAlchemyEventRepository,
) -> None:
    for i in range(1, 4):
        event_repo.save(_make_event(f"e{i}"))
    from app.operator.service import OperatorService

    service = OperatorService(
        event_repository=event_repo,
        entity_repository=SQLAlchemyEntityRepository(
            session_manager=event_repo.session_manager
        ),
        relation_repository=SQLAlchemyRelationRepository(
            session_manager=event_repo.session_manager
        ),
    )
    assert service.max_durable_seq() == 3
    after = service.events_after_seq(1)
    assert [a["seq"] for a in after] == [2, 3]
    assert [a["event"]["event_id"] for a in after] == ["e2", "e3"]
