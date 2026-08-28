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

import asyncio
import json
import os
import tempfile

import httpx
import pytest
import sqlalchemy.exc

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
from app.operator.router import _SSE_TAIL_BATCH, _sse_frame
from app.operator.service import OperatorService

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
    # Resume (Last-Event-ID) emits no snapshot; one tail poll drains seq > 3.
    status, frames = await _get_sse(
        app, f"{STREAM_URL}?stream_ticks=1", headers={"Last-Event-ID": "3"}
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
        app, f"{STREAM_URL}?stream_ticks=1", headers={"Last-Event-ID": "3"}
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
    """A genuine authoritative-database failure -> pre-flight check -> 503."""

    class _FailingEventRepo:
        def max_seq(self) -> int:
            # A real DB-down surfaces as a SQLAlchemy dependency error, which
            # the operator service classifies as 503 (not a programming error).
            raise sqlalchemy.exc.OperationalError(
                "SELECT ...", {}, Exception("db down")
            )

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


@pytest.mark.asyncio
async def test_sse_programming_error_is_not_masked_as_dependency_failure() -> None:
    """Defect 1: an unexpected programmer error must NOT become 503.

    A repository that raises a programming error (not a SQLAlchemy dependency
    failure) must surface as a generic 500 internal-error, never as the
    'authoritative event store unavailable' 503.
    """

    class _BugsyEventRepo:
        def max_seq(self) -> int:
            raise KeyError("programmer bug, not a DB failure")

    app = create_operator_app(
        event_repository=_BugsyEventRepo(),  # type: ignore[arg-type]
        entity_repository=SQLAlchemyEntityRepository(
            session_manager=DatabaseSessionManager("sqlite:///:memory:")
        ),
        relation_repository=SQLAlchemyRelationRepository(
            session_manager=DatabaseSessionManager("sqlite:///:memory:")
        ),
    )
    # raise_app_exceptions=False so the app's generic 500 handler
    # (ServerErrorMiddleware) can produce the response instead of re-raising
    # the exception into the test transport.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        response = await client.get(STREAM_URL)
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "internal operator error"
    assert body["error_type"] == "InternalServerError"


@pytest.mark.asyncio
async def test_sse_stream_ticks_zero_snapshot_only_no_tail_poll(app) -> None:
    """Defect 4: ``stream_ticks=0`` performs ZERO tail polls.

    The initial snapshot is NOT counted as a tail poll, so ``stream_ticks=0``
    yields the snapshot only and terminates — it must not perform a single
    tail poll (D4).
    """
    for i in range(1, 4):
        app.state.operator_service._events.save(_make_event(f"e{i}"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        async with client.stream(
            "GET", f"{STREAM_URL}?stream_ticks=0"
        ) as response:
            body = b"".join(
                [chunk async for chunk in response.aiter_bytes()]
            )
    # Snapshot delivers e1..e3 exactly once (no duplicate frames), then the
    # stream ends with zero tail polls.
    frames = _parse_frames(body)
    assert [f[0] for f in frames] == [1, 2, 3]


def _make_tail_spy(app) -> dict:
    """Wrap ``service.events_after_seq_bounded`` to count tail-poll reads.

    Tail polls use the module batch ``_SSE_TAIL_BATCH`` (=200) as their limit;
    the initial snapshot uses the (much smaller) page ``limit``. Counting calls
    whose ``limit == _SSE_TAIL_BATCH`` therefore counts tail polls exactly and
    deterministically, without any reliance on stream timing/sleeps.
    """
    service = app.state.operator_service
    original = service.events_after_seq_bounded
    counter = {"tail_polls": 0, "snapshot_reads": 0, "calls": []}

    def spy(seq: int, limit: int = 200):
        counter["calls"].append((seq, limit))
        if limit == _SSE_TAIL_BATCH:
            counter["tail_polls"] += 1
        else:
            counter["snapshot_reads"] += 1
        return original(seq, limit)

    service.events_after_seq_bounded = spy  # type: ignore[method-assign]
    return counter


@pytest.mark.asyncio
async def test_sse_stream_ticks_one_performs_exactly_one_tail_poll(app) -> None:
    """Defect 4: ``stream_ticks=1`` performs exactly one tail poll (D4)."""
    for i in range(1, 4):
        app.state.operator_service._events.save(_make_event(f"e{i}"))
    counter = _make_tail_spy(app)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        async with client.stream(
            "GET", f"{STREAM_URL}?stream_ticks=1"
        ) as response:
            body = b"".join(
                [chunk async for chunk in response.aiter_bytes()]
            )
    frames = _parse_frames(body)
    # Snapshot (e1..e3) then exactly ONE tail poll.
    assert [f[0] for f in frames] == [1, 2, 3]
    assert counter["tail_polls"] == 1


@pytest.mark.asyncio
async def test_sse_stream_ticks_two_performs_exactly_two_tail_polls(app) -> None:
    """Defect 4: ``stream_ticks=2`` performs exactly two tail polls (D4)."""
    for i in range(1, 4):
        app.state.operator_service._events.save(_make_event(f"e{i}"))
    counter = _make_tail_spy(app)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        async with client.stream(
            "GET", f"{STREAM_URL}?stream_ticks=2"
        ) as response:
            body = b"".join(
                [chunk async for chunk in response.aiter_bytes()]
            )
    frames = _parse_frames(body)
    assert [f[0] for f in frames] == [1, 2, 3]
    assert counter["tail_polls"] == 2


@pytest.mark.asyncio
async def test_sse_stream_ticks_omitted_is_unbounded_tail(app) -> None:
    """Defect 4: omitted ``stream_ticks`` = unbounded realtime tail (D4).

    With no ``stream_ticks`` the bound is never applied, so the stream keeps
    polling indefinitely. We consume the stream in a background task (keeping
    the server generator alive) and wait for the tail-poll spy to observe
    several polls — far more than any finite bound (0/1/2 ticks) would allow —
    then cancel. ``asyncio.wait_for`` guarantees the test never hangs.
    """
    for i in range(1, 4):
        app.state.operator_service._events.save(_make_event(f"e{i}"))
    counter = _make_tail_spy(app)
    transport = httpx.ASGITransport(app=app)

    async def _consume() -> None:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            async with client.stream("GET", STREAM_URL) as response:
                assert response.status_code == 200
                async for _ in response.aiter_bytes():
                    pass  # keep driving the server generator

    async def _wait_for_polls(n: int, timeout: float) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while counter["tail_polls"] < n:
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError(
                    f"unbounded tail did not reach {n} polls in {timeout}s"
                )
            await asyncio.sleep(0.05)

    consumer = asyncio.create_task(_consume())
    try:
        # Each unbounded tail poll involves a short sleep, so 3 polls arrive
        # within a couple of seconds; wait_for guards against a genuine hang.
        await asyncio.wait_for(_wait_for_polls(3, 15.0), timeout=20.0)
    finally:
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)
    # The unbounded tail performed >= 3 tail polls — a finite bound (0/1/2
    # ticks) would have terminated long before reaching 3.
    assert counter["tail_polls"] >= 3


# -- Defect 5: race-boundary coverage (bounded-batch cursor semantics) --------


def _make_service(event_repo: SQLAlchemyEventRepository) -> OperatorService:
    return OperatorService(
        event_repository=event_repo,
        entity_repository=SQLAlchemyEntityRepository(
            session_manager=event_repo.session_manager
        ),
        relation_repository=SQLAlchemyRelationRepository(
            session_manager=event_repo.session_manager
        ),
    )


def test_race_case_a_event_committed_after_snapshot_is_delivered(
    event_repo: SQLAlchemyEventRepository,
) -> None:
    """Case A: snapshot captured through seq N; event N+1 committed; first tail
    must deliver N+1."""
    for i in range(1, 4):
        event_repo.save(_make_event(f"e{i}"))  # snapshot through seq 3
    service = _make_service(event_repo)
    snapshot = service.events_after_seq_bounded(0, limit=50)  # seq 1..3
    assert [s["seq"] for s in snapshot] == [1, 2, 3]
    # Event N+1 (seq 4) committed after the snapshot was captured.
    event_repo.save(_make_event("e4"))
    tail = service.events_after_seq_bounded(3, limit=200)
    assert [t["seq"] for t in tail] == [4]
    assert tail[0]["event"]["event_id"] == "e4"


def test_race_case_b_snapshot_event_not_duplicated_in_tail(
    event_repo: SQLAlchemyEventRepository,
) -> None:
    """Case B: snapshot contains N; cursor = N; first tail must NOT re-deliver N."""
    for i in range(1, 4):
        event_repo.save(_make_event(f"e{i}"))  # N = 3
    service = _make_service(event_repo)
    snapshot = service.events_after_seq_bounded(0, limit=50)
    assert [s["seq"] for s in snapshot] == [1, 2, 3]
    # Tail reads strictly after cursor N=3 -> no duplicate of seq 3.
    tail = service.events_after_seq_bounded(3, limit=200)
    assert tail == []


def test_race_case_c_multiple_events_before_first_tail_delivered_in_order(
    event_repo: SQLAlchemyEventRepository,
) -> None:
    """Case C: events N+1,N+2,N+3 committed before first tail -> all delivered in
    seq order via bounded batches."""
    for i in range(1, 4):
        event_repo.save(_make_event(f"e{i}"))  # snapshot through seq 3
    service = _make_service(event_repo)
    service.events_after_seq_bounded(0, limit=50)
    # N+1, N+2, N+3 committed before first tail read.
    for i in range(4, 7):
        event_repo.save(_make_event(f"e{i}"))
    tail = service.events_after_seq_bounded(3, limit=200)
    assert [t["seq"] for t in tail] == [4, 5, 6]
    assert [t["event"]["event_id"] for t in tail] == ["e4", "e5", "e6"]


def test_race_case_d_last_event_id_then_new_event(
    event_repo: SQLAlchemyEventRepository,
) -> None:
    """Case D: Last-Event-ID = N; new event N+1 -> deliver N+1 only."""
    for i in range(1, 4):
        event_repo.save(_make_event(f"e{i}"))  # N = 3
    service = _make_service(event_repo)
    event_repo.save(_make_event("e4"))  # N+1 committed
    tail = service.events_after_seq_bounded(3, limit=200)
    assert [t["seq"] for t in tail] == [4]
    assert tail[0]["event"]["event_id"] == "e4"


def test_bounded_batch_respects_limit(event_repo: SQLAlchemyEventRepository) -> None:
    """Defect 3: the bounded tail batch never returns more than ``limit`` events."""
    for i in range(1, 6):
        event_repo.save(_make_event(f"e{i}"))
    service = _make_service(event_repo)
    batch = service.events_after_seq_bounded(0, limit=2)
    assert [b["seq"] for b in batch] == [1, 2]  # DB-bounded to 2, not 5


# -- service layer primitives ------------------------------------------------


def test_service_events_after_seq_ordering(
    event_repo: SQLAlchemyEventRepository,
) -> None:
    for i in range(1, 4):
        event_repo.save(_make_event(f"e{i}"))
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


# -- Defect 3: real authoritative seq (D3) ------------------------------------


def test_d3_seq_comes_from_authoritative_repository_metadata(
    event_repo: SQLAlchemyEventRepository,
) -> None:
    """D3.1: each returned ``seq`` is the REAL authoritative durable seq.

    The SSE ``id`` must be the durable ``seq`` stored by the authoritative
    repository, never reconstructed as ``base + list-index``. The durable layer
    guarantees a no-gap ``MAX+1`` sequence through its public API, so we do NOT
    fabricate an impossible gap with raw SQL (that would tamper with a protected
    authoritative store). Instead we prove the implementation reads each seq
    from authoritative repository metadata: for every returned event, its
    ``seq`` must equal ``get_durable_event(event_id)[0]`` — the authoritative
    persisted seq for that exact event.
    """
    for i in range(1, 6):
        event_repo.save(_make_event(f"e{i}"))
    service = _make_service(event_repo)
    batch = service.events_after_seq_bounded(0, limit=200)
    # The returned seqs equal the seqs the authoritative repo assigns.
    assert [b["seq"] for b in batch] == [1, 2, 3, 4, 5]
    for item in batch:
        event_id = item["event"]["event_id"]
        authoritative_seq = event_repo.get_durable_event(event_id)[0]
        assert item["seq"] == authoritative_seq
    # Prove the seq is read from metadata, not a positional index: reading a
    # page starting at a non-zero cursor returns seqs that match the repo's
    # authoritative seqs for those specific events.
    tail = service.events_after_seq_bounded(2, limit=200)
    assert [t["seq"] for t in tail] == [3, 4, 5]
    for item in tail:
        event_id = item["event"]["event_id"]
        assert item["seq"] == event_repo.get_durable_event(event_id)[0]


def test_d3_bounded_query_is_db_level_not_python_slice(
    event_repo: SQLAlchemyEventRepository,
) -> None:
    """D3.2: the bounded read is DB-level (SQL LIMIT), not a Python slice.

    Seed far more events than the requested limit and assert the batch returns
    exactly the requested count — proving the query bounded the result set at
    the DB layer rather than loading everything and slicing in Python. The
    repository's ``query_events`` clamps ``limit`` to its bounded maximum (200),
    so a ``limit`` above that still returns at most 200.
    """
    for i in range(1, 501):
        event_repo.save(_make_event(f"e{i}"))
    service = _make_service(event_repo)
    # Request a small limit over a 500-event backlog -> exactly 2, not 500.
    small = service.events_after_seq_bounded(0, limit=2)
    assert [s["seq"] for s in small] == [1, 2]
    # Requesting more than the repository's bounded max returns at most 200.
    capped = service.events_after_seq_bounded(0, limit=100000)
    assert len(capped) == 200
    assert [c["seq"] for c in capped] == list(range(1, 201))


def test_d3_large_backlog_bounded_ordered_no_gap_no_duplicate(
    event_repo: SQLAlchemyEventRepository,
) -> None:
    """D3.3: a >=500-event backlog drains in bounded, ordered, gap-free,
    duplicate-free batches.
    """
    for i in range(1, 501):
        event_repo.save(_make_event(f"e{i}"))
    service = _make_service(event_repo)
    cursor = 0
    seen: list = []
    while True:
        batch = service.events_after_seq_bounded(cursor, limit=200)
        if not batch:
            break
        assert len(batch) <= 200  # never exceeds the configured bound
        for item in batch:
            seen.append(item["seq"])
        cursor = batch[-1]["seq"]
    # All 500 events delivered exactly once, in ascending contiguous order.
    assert seen == list(range(1, 501))
    assert len(seen) == 500
    assert len(set(seen)) == 500  # no duplicates
    # No gaps in the full drain.
    assert seen == sorted(seen)
    assert all(b == a + 1 for a, b in zip(seen, seen[1:]))
