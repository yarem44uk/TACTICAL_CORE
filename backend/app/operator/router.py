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
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.operator.service import (
    InvalidRequestError,
    NotFoundError,
    OperatorService,
    ReadDependencyUnavailableError,
)

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
) -> JSONResponse:
    """GET /api/v1/operator/events — cursor-paginated, filterable event feed.

    Query parameters:
      source, event_type, from_time, to_time, limit (bounded to [1, 200]),
      cursor (opaque keyset continuation).

    ``severity`` filtering is DEFERRED (not implemented in WO-037-02).
    """
    service: OperatorService = request.app.state.operator_service
    result = service.list_events(
        source=source,
        event_type=event_type,
        from_time=_parse_time(from_time, "from_time"),
        to_time=_parse_time(to_time, "to_time"),
        limit=_parse_limit(limit),
        cursor=_parse_cursor(cursor),
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

    ``stream_ticks`` (optional): bound the number of tail-poll iterations. When
    provided, the stream ends normally after that many polls; when omitted the
    stream is the infinite realtime tail. This makes the endpoint deterministic
    and testable without a live indefinite connection.

    The stream is a seq-ordered tail over the authoritative event log. Event
    filtering (source / event_type / time range) is not part of the best-effort
    SSE stream; the authoritative filtered view remains the REST
    ``GET /api/v1/operator/events`` endpoint.

    Read-only: this endpoint only reads the authoritative repository. It never
    writes, never dispatches, never retries, never modifies checkpoint or
    projection state, and never creates a second event store.
    """
    service: OperatorService = request.app.state.operator_service

    page_limit = _parse_limit(limit) if limit is not None else _SSE_SNAPSHOT_DEFAULT

    ticks: Optional[int] = None
    if stream_ticks is not None:
        if not isinstance(stream_ticks, int) or isinstance(stream_ticks, bool) or stream_ticks < 0:
            raise InvalidRequestError("stream_ticks must be a non-negative integer")
        ticks = stream_ticks

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
    # cannot be changed after the first streamed byte).
    service.max_durable_seq()

    async def _stream():  # noqa: ANN202 - async generator inferred
        cursor: Optional[int] = last_seq
        remaining_ticks: Optional[int] = ticks
        try:
            # Fresh connect: bounded initial snapshot of the most recent events.
            if cursor is None:
                max_seq = service.max_durable_seq()
                snapshot_start = max(0, max_seq - page_limit)
                for item in service.events_after_seq(snapshot_start):
                    cursor = item["seq"]
                    yield _sse_frame(cursor, item)
                if cursor is None:
                    cursor = max_seq

            # Tail loop: poll the authoritative log for new events (best-effort).
            assert cursor is not None
            while True:
                items = service.events_after_seq(cursor)
                for item in items:
                    cursor = item["seq"]
                    yield _sse_frame(cursor, item)
                # Keepalive comment frame keeps the connection alive and lets
                # a dropped client be detected. Standard SSE; no durable state.
                yield ": keepalive\n\n"
                if remaining_ticks is not None:
                    remaining_ticks -= 1
                    if remaining_ticks < 0:
                        return
                await asyncio.sleep(_SSE_POLL_SECONDS)
        except asyncio.CancelledError:
            # Client disconnected / response cancelled. Close cleanly.
            return
        except (ReadDependencyUnavailableError, Exception):  # noqa: BLE001
            # Mid-stream read failure: signal honestly, never mask as success.
            yield _sse_frame(
                None,
                {"event": "error", "error": "authoritative event store unavailable"},
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


@router.get("/entities")
def list_entities(
    request: Request,
    entity_type: Optional[str] = Query(default=None),
) -> JSONResponse:
    """GET /api/v1/operator/entities — active durable entities (by type)."""
    service: OperatorService = request.app.state.operator_service
    result = service.list_entities(entity_type=entity_type)
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
