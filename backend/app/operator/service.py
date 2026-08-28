"""WO-037-02 — Operator query service (read-only).

The operator service is the thin query/translation layer between the HTTP
router and the authoritative durable repositories. It is deliberately free of
any HTTP framework import so it stays a plain, deterministic, unit-testable
Python layer.

Architecture (ADR-011):
    HTTP request -> router -> operator service -> authoritative repository -> SQLite

The service is a CONSUMER of the authoritative repositories. It never writes,
never dispatches, never retries, never reconstructs, never acknowledges and
never alters durable state.

Read-only contract:
  * all queries run against ``SQLAlchemyEventRepository`` (``query_events`` /
    ``get_durable_event``), ``SQLAlchemyEntityRepository`` (``list_all`` /
    ``get``) and ``SQLAlchemyRelationRepository`` (``list_for_entity``);
  * no insert / update / delete / commit of application state.

Serialization is deterministic and JSON-serialisable. Timestamps are ISO-8601
UTC (the canonical ``Event.to_dict`` and the repository ``_row_to_dict``
helpers already produce ISO-8601 strings).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.entity_relations.sqlalchemy_relation_repository import (
    SQLAlchemyRelationRepository,
)
from app.entity_repository.sqlalchemy_entity_repository import (
    SQLAlchemyEntityRepository,
)
from app.event.event import Event
from app.event_repository.durable.sqlalchemy_event_repository import (
    SQLAlchemyEventRepository,
)


class OperatorError(Exception):
    """Base error raised by the operator service.

    ``status_code`` carries the intended HTTP error contract value (400 / 404 /
    503 / 500). Subclasses set a sensible default.
    """

    status_code: int = 500

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class InvalidRequestError(OperatorError):
    """Invalid request parameter (HTTP 400)."""

    status_code = 400


class NotFoundError(OperatorError):
    """Requested object does not exist (HTTP 404)."""

    status_code = 404


class ReadDependencyUnavailableError(OperatorError):
    """Authoritative database/read dependency is unavailable (HTTP 503)."""

    status_code = 503


def _event_to_dict(event: Event) -> Dict[str, Any]:
    """Serialize one canonical Event deterministically (ISO-8601 UTC)."""
    data = event.to_dict()
    # ``to_dict`` already emits ISO-8601 strings for timestamp / created_at and
    # a JSON-safe payload/metadata; surface event_status explicitly.
    return data


class OperatorService:
    """Read-only query facade over the authoritative durable repositories.

    Args:
        event_repository: authoritative durable event repository.
        entity_repository: authoritative durable entity repository.
        relation_repository: authoritative durable relation repository.
    """

    def __init__(
        self,
        event_repository: SQLAlchemyEventRepository,
        entity_repository: SQLAlchemyEntityRepository,
        relation_repository: SQLAlchemyRelationRepository,
    ) -> None:
        self._events = event_repository
        self._entities = entity_repository
        self._relations = relation_repository

    # -- events --------------------------------------------------------------

    def list_events(
        self,
        *,
        source: Optional[str] = None,
        event_type: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 50,
        cursor: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return a deterministic, cursor-paginated event feed page.

        Delegates the actual query to the authoritative repository's
        ``query_events`` (WO-037-01 keyset pagination). The service only
        validates/normalises request parameters and shapes the response.

        Raises:
            InvalidRequestError: malformed cursor / invalid limit / inverted
                time range (HTTP 400).
            ReadDependencyUnavailableError: authoritative read dependency
                unavailable (HTTP 503).
        """
        events, next_cursor = self._query_events(
            source=source,
            event_type=event_type,
            from_time=from_time,
            to_time=to_time,
            limit=limit,
            cursor=cursor,
        )
        return {
            "events": [_event_to_dict(e) for e in events],
            "next_cursor": next_cursor,
        }

    def _query_events(self, **kwargs: Any) -> "tuple[List[Event], Optional[int]]":
        try:
            return self._events.query_events(**kwargs)
        except ValueError as exc:
            raise InvalidRequestError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - translate to 503
            raise ReadDependencyUnavailableError(
                "authoritative event store unavailable"
            ) from exc

    def get_event(self, event_id: str) -> Dict[str, Any]:
        """Return one authoritative durable event by canonical event_id.

        Raises:
            NotFoundError: event_id not durably persisted (HTTP 404).
            ReadDependencyUnavailableError: read dependency unavailable (503).
        """
        try:
            result = self._events.get_durable_event(event_id)
        except Exception as exc:  # noqa: BLE001
            raise ReadDependencyUnavailableError(
                "authoritative event store unavailable"
            ) from exc
        if result is None:
            raise NotFoundError(f"event {event_id!r} not found")
        seq, event = result
        data = _event_to_dict(event)
        data["seq"] = seq
        return data

    # -- entities ------------------------------------------------------------

    def list_entities(
        self, *, entity_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return all active durable entities (optionally filtered by type)."""
        try:
            rows = self._entities.list_all(entity_type=entity_type)
        except Exception as exc:  # noqa: BLE001
            raise ReadDependencyUnavailableError(
                "authoritative entity store unavailable"
            ) from exc
        return {"entities": rows}

    def get_entity(self, entity_id: str) -> Dict[str, Any]:
        """Return one active durable entity by identity."""
        try:
            row = self._entities.get(entity_id)
        except Exception as exc:  # noqa: BLE001
            raise ReadDependencyUnavailableError(
                "authoritative entity store unavailable"
            ) from exc
        if row is None:
            raise NotFoundError(f"entity {entity_id!r} not found")
        return {"entity": row}

    # -- relations -----------------------------------------------------------

    def list_entity_relations(
        self, entity_id: str, *, status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return the durable relations involving one entity.

        If the entity does not exist authoritatively, a 404 is returned so the
        caller can distinguish "no relations" from "unknown entity".
        """
        # Confirm the entity exists (read-only) before listing its relations.
        try:
            entity = self._entities.get(entity_id)
        except Exception as exc:  # noqa: BLE001
            raise ReadDependencyUnavailableError(
                "authoritative entity store unavailable"
            ) from exc
        if entity is None:
            raise NotFoundError(f"entity {entity_id!r} not found")
        try:
            rows = self._relations.list_for_entity(entity_id, status=status)
        except Exception as exc:  # noqa: BLE001
            raise ReadDependencyUnavailableError(
                "authoritative relation store unavailable"
            ) from exc
        return {"entity_id": entity_id, "relations": rows}

    # -- health --------------------------------------------------------------

    def health(self) -> Dict[str, Any]:
        """Report only authoritative, actually-existing metrics.

        Metrics:
          * ``durable_events`` — authoritative durable event count;
          * ``durable_entities`` — active durable entity count;
          * ``relation_projection`` — authoritative ``source_config`` is not a
            durable projection concern here, so no fabricated projection
            checkpoint is reported;
          * ``last_ingestion`` — ``unavailable`` (the authoritative system does
            not persist a last-ingestion timestamp).

        Health never writes to durable state.
        """
        try:
            event_count = self._events.count()
            entity_count = self._entities.count()
        except Exception as exc:  # noqa: BLE001
            raise ReadDependencyUnavailableError(
                "authoritative read dependency unavailable"
            ) from exc
        return {
            "status": "ok",
            "durable_events": event_count,
            "durable_entities": entity_count,
            "last_ingestion": "unavailable",
        }
