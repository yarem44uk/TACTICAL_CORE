"""WO-037-02 — Operator API router (GET-only).

The router is deliberately thin: it parses HTTP query/path parameters, calls the
read-only :class:`OperatorService`, and maps service errors to the structured
HTTP error contract. No repository or business logic lives here.

Allowed methods (WO-037-02): only GET. Mutation methods are not registered;
FastAPI returns 405 for unsupported methods on the registered routes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.operator.recording_access import (
    InvalidRecordingRangeError,
    UnsatisfiableRangeError,
    parse_range,
)
from app.operator.service import (
    InvalidRequestError,
    NotFoundError,
    OperatorService,
    ReadDependencyUnavailableError,
    _normalize_severity,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/operator", tags=["operator"])


def _parse_cursor(value: Optional[str]) -> Optional[int]:
    """Parse an optional cursor query parameter into an int (or None).

    A malformed cursor (non-integer) is a client error -> 400. This is handled
    by raising InvalidRequestError, which the router exception handler maps to
    HTTP 400.
    """
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise InvalidRequestError("cursor must be an integer seq") from None


def _parse_limit(value: Optional[int]) -> int:
    """Validate/normalise the limit query parameter (bounded at the repo)."""
    if value is None:
        return 50
    if value < 1:
        raise InvalidRequestError("limit must be a positive integer")
    return value


def _parse_offset(value: Optional[int]) -> int:
    """Validate/normalise the offset query parameter."""
    if value is None:
        return 0
    if value < 0:
        raise InvalidRequestError("offset must be a non-negative integer")
    return value


def _parse_time(value: Optional[str], name: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp query parameter (naive treated as UTC)."""
    if value is None or value == "":
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise InvalidRequestError(f"{name} must be an ISO-8601 timestamp") from None


@router.get("/events")
def list_events(
    request: Request,
    source: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    from_time: Optional[str] = Query(default=None),
    to_time: Optional[str] = Query(default=None),
    limit: Optional[int] = Query(default=None),
    cursor: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
) -> JSONResponse:
    """GET /api/v1/operator/events — cursor-paginated, filterable event feed.

    Query parameters:
      source, event_type, from_time, to_time, limit (bounded to [1, 200]),
      cursor (opaque keyset continuation), severity (WO-037-06; one of
      INFO / WARNING / THREAT / CRITICAL / UNCLASSIFIED).

    ``severity`` filters the returned page by the derived baseline
    classification (computed on demand, never persisted). It is a
    consumer-side view filter; it never mutates event data.
    """
    service: OperatorService = request.app.state.operator_service
    result = service.list_events(
        source=source,
        event_type=event_type,
        from_time=_parse_time(from_time, "from_time"),
        to_time=_parse_time(to_time, "to_time"),
        limit=_parse_limit(limit),
        cursor=_parse_cursor(cursor),
        severity=severity,
    )
    return JSONResponse(result)


# -- SSE realtime (WO-037-04) -------------------------------------------------
# Best-effort server-sent event stream over the authoritative durable event
# log (ADR-011 §12). REST remains the authoritative fallback; SSE publication
# occurs only after durable state is committed/visible and never mutates
# durable state, checkpoints or projections.

# Poll interval between reads of the authoritative event log (best-effort, no
# durable state). Kept as a module constant so tests can be deterministic.
_SSE_POLL_SECONDS = 0.5
# Bounded initial snapshot page size (clamped to the repository maximum).
_SSE_SNAPSHOT_DEFAULT = 50
# Bounded operator tail batch size (WO-037-04 Defect 3). Each poll reads at
# most this many durable events from the authoritative log so a burst never
# materialises the whole post-cursor log in memory.
_SSE_TAIL_BATCH = 200


def _sse_frame(event_id: Optional[int], data: dict) -> str:
    """Format one SSE data frame with a deterministic ``id``."""
    lines = []
    if event_id is not None:
        lines.append(f"id: {int(event_id)}")
    lines.append("data: " + json.dumps(data, separators=(",", ":")))
    return "\n".join(lines) + "\n\n"


@router.get("/events/stream")
async def events_stream(
    request: Request,
    limit: Optional[int] = Query(default=None),
    stream_ticks: Optional[int] = Query(default=None),
    severity: Optional[str] = Query(default=None),
) -> StreamingResponse:
    """GET /api/v1/operator/events/stream — best-effort SSE event stream.

    Frames are ``text/event-stream`` with deterministic ``id`` = durable seq.

    Reconnect: the client sends ``Last-Event-ID: <seq>``; the stream resumes
    from the authoritative durable log at ``seq > Last-Event-ID`` via the
    existing read-only repository ``iter_after_seq``. ``Last-Event-ID`` is a
    client resume cursor, NOT a new persistent SSE checkpoint.

    Fresh connect (no ``Last-Event-ID``): a bounded initial snapshot of the
    most recent ``limit`` durable events is emitted, then new events are
    tailed by polling the authoritative log (best-effort).

    ``stream_ticks`` (optional, testing knob): bounds the number of tail-poll
    cycles performed after the initial snapshot to EXACTLY that many polls.
    The initial snapshot is NOT counted as a tail poll. Therefore:
    ``stream_ticks=0`` yields the initial snapshot only (zero tail polls) and
    terminates; ``stream_ticks=1`` yields the snapshot plus exactly one tail
    poll; ``stream_ticks=2`` yields the snapshot plus exactly two tail polls.
    When ``stream_ticks`` is omitted, the stream is the infinite realtime tail
    (production default, never finite). This keeps the endpoint deterministic
    and testable without a live indefinite connection.

    The stream is a seq-ordered tail over the authoritative event log. Event
    filtering (source / event_type / time range) is not part of the best-effort
    SSE stream; the authoritative filtered view remains the REST
    ``GET /api/v1/operator/events`` endpoint.

    ``severity`` (optional, WO-037-06) filters the emitted frames by the
    derived baseline classification (computed on demand, never persisted). It
    is a consumer-side view filter applied between the authoritative read and
    emission; it never mutates durable state and never redesigns the SSE
    contract. When omitted, every event is emitted (backwards compatible).

    Read-only: this endpoint only reads the authoritative repository. It never
    writes, never dispatches, never retries, never modifies checkpoint or
    projection state, and never creates a second event store.

    Blocking repository reads (synchronous SQLAlchemy) are offloaded with
    ``asyncio.to_thread`` so they never block the asyncio event loop, and the
    tail is read in bounded batches via ``events_after_seq_bounded``.
    """
    service: OperatorService = request.app.state.operator_service

    page_limit = _parse_limit(limit) if limit is not None else _SSE_SNAPSHOT_DEFAULT

    ticks: Optional[int] = None
    if stream_ticks is not None:
        if not isinstance(stream_ticks, int) or isinstance(stream_ticks, bool) or stream_ticks < 0:
            raise InvalidRequestError("stream_ticks must be a non-negative integer")
        ticks = stream_ticks

    # Validate/normalise the optional severity filter BEFORE any stream byte is
    # emitted, so an invalid severity maps to HTTP 400 (the status code cannot
    # be changed after the first streamed byte).
    severity = _normalize_severity(severity) if severity is not None else None

    # Last-Event-ID: client resume cursor (integer durable seq). Not durable.
    raw_last = request.headers.get("last-event-id")
    last_seq: Optional[int] = None
    if raw_last not in (None, ""):
        try:
            last_seq = int(raw_last)
        except (TypeError, ValueError):
            raise InvalidRequestError("Last-Event-ID must be an integer seq") from None

    # Pre-flight availability check BEFORE streaming starts, so a dead
    # authoritative read dependency can still map to HTTP 503 (the status code
    # cannot be changed after the first streamed byte). Offloaded so the check
    # does not block the event loop either.
    await asyncio.to_thread(service.max_durable_seq)

    async def _stream():  # noqa: ANN202 - async generator inferred
        cursor: Optional[int] = last_seq
        remaining_ticks: Optional[int] = ticks
        try:
            # Fresh connect: bounded initial snapshot of the most recent events.
            if cursor is None:
                max_seq = await asyncio.to_thread(service.max_durable_seq)
                snapshot_start = max(0, max_seq - page_limit)
                snapshot_items = await asyncio.to_thread(
                    service.events_after_seq_bounded, snapshot_start, page_limit
                )
                for item in snapshot_items:
                    cursor = item["seq"]
                    if severity is None or item.get("event", {}).get("severity") == severity:
                        yield _sse_frame(cursor, item)
                if cursor is None:
                    cursor = max_seq

            # Tail loop: drain the authoritative log in bounded batches
            # (best-effort), advancing the cursor only past events actually
            # emitted — no loss, no duplication, no second event store.
            # ``stream_ticks=N`` performs EXACTLY N tail polls (the initial
            # snapshot is NOT a tail poll); ``None`` = unbounded realtime tail.
            assert cursor is not None
            while True:
                # Zero-poll bound: exit BEFORE doing any tail read. This makes
                # ``stream_ticks=0`` terminate after the snapshot alone without
                # relying on a decrement-after-poll (D4).
                if remaining_ticks is not None and remaining_ticks <= 0:
                    return
                # One tail poll: drain all currently-available events in
                # bounded batches.
                while True:
                    items = await asyncio.to_thread(
                        service.events_after_seq_bounded, cursor, _SSE_TAIL_BATCH
                    )
                    if not items:
                        break
                    for item in items:
                        cursor = item["seq"]
                        if severity is None or item.get("event", {}).get("severity") == severity:
                            yield _sse_frame(cursor, item)
                # Keepalive comment frame keeps the connection alive and lets
                # a dropped client be detected. Standard SSE; no durable state.
                yield ": keepalive\n\n"
                if remaining_ticks is not None:
                    remaining_ticks -= 1
                    if remaining_ticks <= 0:
                        return
                await asyncio.sleep(_SSE_POLL_SECONDS)
        except asyncio.CancelledError:
            # Client disconnected / response cancelled. Close cleanly.
            return
        except ReadDependencyUnavailableError:
            # Expected authoritative read-dependency failure mid-stream:
            # signal honestly as a degraded SSE error, never mask as success.
            yield _sse_frame(
                None,
                {"event": "error", "error": "authoritative event store unavailable"},
            )
            return
        except Exception:  # noqa: BLE001 - unexpected, log and close safely
            # An unexpected programmer/runtime error (KeyError, TypeError,
            # serialization, AttributeError, ...) is NOT a database failure. It
            # is logged server-side and surfaced as a generic internal error
            # frame — the traceback/secret material is never sent to the client.
            logger.exception("unexpected error in SSE stream")
            yield _sse_frame(
                None,
                {"event": "error", "error": "internal operator error"},
            )
            return

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

@router.get("/events/{event_id}")
def get_event(request: Request, event_id: str) -> JSONResponse:
    """GET /api/v1/operator/events/{event_id} — one authoritative event."""
    service: OperatorService = request.app.state.operator_service
    result = service.get_event(event_id)
    return JSONResponse(result)


# -- recording evidence access (WO-062) --------------------------------------
# Read-only, identity-based WAV serving.  The client supplies ONLY the canonical
# recording identity in the URL; the server resolves the recording from its
# canonical identity, confines the resolved path to the authoritative archive
# root, re-verifies SHA-256, and serves the WAV with RFC 9110 byte-range support.

# Streaming chunk size for the response body (bounded, never loads the whole
# file into memory merely to serve a range).
_STREAM_CHUNK = 1 << 16


def _recording_response_headers(artifact) -> dict:
    """Common success headers for a WAV artifact response."""
    return {
        "Accept-Ranges": "bytes",
        "Content-Type": artifact.mime_type,
    }


@router.get("/recordings/{recording_id}")
async def get_recording(
    request: Request,
    recording_id: str,
    range_header: Optional[str] = Header(default=None, alias="Range"),
) -> Response:
    """GET /api/v1/operator/recordings/{recording_id} — authenticated WAV evidence.

    The client provides only the canonical recording identity (``audio_recording_id``).
    The server resolves it to the authoritative WAV artifact, confines the path to
    the configured archive root, re-verifies SHA-256, and streams the WAV with
    RFC 9110 single byte-range support.

    Responses:
        * 200 OK  — full artifact (``Content-Type: audio/wav``,
          ``Content-Length``, ``Accept-Ranges: bytes``).
        * 206 Partial Content — satisfiable ``Range`` (``Content-Range``,
          ``Content-Length``, ``Accept-Ranges: bytes``).
        * 416 Range Not Satisfiable — unsatisfiable ``Range``
          (``Content-Range: bytes */<size>``).
        * 400 — malformed/unsupported ``Range``.
        * 404 — recording identity unknown or artifact unavailable/invalid.

    Read-only: never mutates the WAV, MP3, metadata, Event, Observation or
    Journal.  The integrity check runs before any media byte is exposed.
    """
    service: OperatorService = request.app.state.operator_service
    # The resolver performs SHA-256 over the artifact; offload the blocking IO
    # so it never blocks the asyncio event loop.
    artifact = await asyncio.to_thread(service.get_recording, recording_id)
    size = artifact.size

    start, end = 0, size - 1
    status_code = 200
    headers = _recording_response_headers(artifact)

    if range_header:
        try:
            start, end = parse_range(range_header, size)
        except UnsatisfiableRangeError:
            return JSONResponse(
                status_code=416,
                content={
                    "detail": "range not satisfiable",
                    "error_type": "RangeNotSatisfiable",
                },
                headers={
                    "Accept-Ranges": "bytes",
                    "Content-Range": f"bytes */{size}",
                },
            )
        except InvalidRecordingRangeError:
            return JSONResponse(
                status_code=400,
                content={
                    "detail": "invalid range",
                    "error_type": "InvalidRequestError",
                },
                headers={"Accept-Ranges": "bytes"},
            )
        status_code = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    headers["Content-Length"] = str(end - start + 1)

    def _iter_bytes():
        with open(artifact.path, "rb") as fh:
            fh.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = fh.read(min(_STREAM_CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        _iter_bytes(),
        status_code=status_code,
        headers=headers,
        media_type=artifact.mime_type,
    )


@router.get("/entities")
def list_entities(
    request: Request,
    entity_type: Optional[str] = Query(default=None),
) -> JSONResponse:
    """GET /api/v1/operator/entities — active durable entities (by type)."""
    service: OperatorService = request.app.state.operator_service
    result = service.list_entities(entity_type=entity_type)
    return JSONResponse(result)


@router.get("/observations")
def list_observations(
    request: Request,
    source: Optional[str] = Query(default=None),
    observation_type: Optional[str] = Query(default=None),
    from_time: Optional[str] = Query(default=None),
    to_time: Optional[str] = Query(default=None),
    limit: Optional[int] = Query(default=None),
    offset: Optional[int] = Query(default=None),
) -> JSONResponse:
    """GET /api/v1/operator/observations — observations ordered by event time.

    WO-060 read-model endpoint.  Observations are ordered by ``occurred_at``
    (canonical event time) DESC with deterministic tie-breaking, distinct from
    the ingestion ``timestamp``.  Query parameters:
      source, observation_type, from_time, to_time (ISO-8601, on occurred_at),
      limit (default 50), offset (default 0).

    ``radio.recording`` observations are visible here and their recording
    evidence (wav/mp3 refs, sha256, duration, content_id) is preserved in
    ``evidence_payload``.
    """
    service: OperatorService = request.app.state.operator_service
    result = service.list_observations(
        source=source,
        observation_type=observation_type,
        from_time=_parse_time(from_time, "from_time"),
        to_time=_parse_time(to_time, "to_time"),
        limit=_parse_limit(limit),
        offset=_parse_offset(offset),
    )
    return JSONResponse(result)


@router.get("/entities/{entity_id}")
def get_entity(request: Request, entity_id: str) -> JSONResponse:
    """GET /api/v1/operator/entities/{entity_id} — one active entity."""
    service: OperatorService = request.app.state.operator_service
    result = service.get_entity(entity_id)
    return JSONResponse(result)


@router.get("/entities/{entity_id}/relations")
def list_entity_relations(
    request: Request,
    entity_id: str,
    status: Optional[str] = Query(default=None),
) -> JSONResponse:
    """GET /api/v1/operator/entities/{entity_id}/relations — durable relations."""
    service: OperatorService = request.app.state.operator_service
    result = service.list_entity_relations(entity_id, status=status)
    return JSONResponse(result)


@router.get("/health")
def health(request: Request) -> JSONResponse:
    """GET /api/v1/operator/health — authoritative read-only health metrics."""
    service: OperatorService = request.app.state.operator_service
    result = service.health()
    return JSONResponse(result)
