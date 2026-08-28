"""WO-037-02 — Operator API router (GET-only).

The router is deliberately thin: it parses HTTP query/path parameters, calls the
read-only :class:`OperatorService`, and maps service errors to the structured
HTTP error contract. No repository or business logic lives here.

Allowed methods (WO-037-02): only GET. Mutation methods are not registered;
FastAPI returns 405 for unsupported methods on the registered routes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.operator.service import (
    InvalidRequestError,
    NotFoundError,
    OperatorService,
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
