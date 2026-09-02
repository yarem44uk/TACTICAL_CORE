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

import sqlalchemy.exc

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
from app.operator.severity import (
    Severity,
    classify,
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
    """Serialize one canonical Event deterministically (ISO-8601 UTC).

    The derived baseline ``severity`` (WO-037-06) is computed on demand from
    the event's deterministic facts (event_type + source) and is a read-only,
    consumer-side annotation. It is NEVER persisted, never written to the
    event/schema/database, and cannot be altered by the operator.
    """
    data = event.to_dict()
    data["severity"] = classify(event).value
    return data


def _normalize_severity(value: str) -> str:
    """Validate/normalise a severity filter value to its canonical form.

    Accepts any case/whitespace variant of one of the five baseline severities
    (INFO / WARNING / THREAT / CRITICAL / UNCLASSIFIED). A value that is not a
    valid baseline severity is a client error -> 400.

    Returns the canonical uppercase value.
    """
    if value is None:
        raise InvalidRequestError("severity must not be null")
    normalized = str(value).strip().upper()
    valid = {s.value for s in Severity}
    if normalized not in valid:
        raise InvalidRequestError(
            f"severity must be one of {', '.join(sorted(valid))}"
        )
    return normalized


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
        severity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a deterministic, cursor-paginated event feed page.

        Delegates the actual query to the authoritative repository's
        ``query_events`` (WO-037-01 keyset pagination). The service only
        validates/normalises request parameters and shapes the response.

        ``severity`` (optional, WO-037-06) filters the returned page by the
        derived baseline classification. Because baseline severity is computed
        on demand and NEVER durably persisted, this is a consumer-side view
        filter applied to the already-fetched page (the authoritative cursor
        pagination is unchanged). It never mutates event data.

        Raises:
            InvalidRequestError: malformed cursor / invalid limit / inverted
                time range / invalid severity (HTTP 400).
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
        if severity is not None:
            severity = _normalize_severity(severity)
            events = [e for e in events if classify(e).value == severity]
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

    # -- SSE realtime read layer (WO-037-04) ---------------------------------

    def max_durable_seq(self) -> int:
        """Return the highest authoritative durable ``seq`` (or 0 if empty).

        Read-only helper used by the SSE stream to determine the current tail
        of the authoritative event log. Never writes, never dispatches, never
        creates durable SSE state.

        Raises:
            ReadDependencyUnavailableError: authoritative read dependency
                unavailable (HTTP 503).
        """
        try:
            return int(self._events.max_seq())
        except ReadDependencyUnavailableError:
            raise
        except sqlalchemy.exc.SQLAlchemyError as exc:
            # A genuine authoritative-database read failure is a dependency
            # failure (503). Unexpected programmer/runtime errors (KeyError,
            # TypeError, serialization, AttributeError, ...) are deliberately
            # NOT translated to 503; they propagate and map to the generic 500
            # internal-error contract (see app.py exception handlers).
            raise ReadDependencyUnavailableError(
                "authoritative event store unavailable"
            ) from exc

    def events_after_seq(self, seq: int) -> List[Dict[str, Any]]:
        """Return authoritative durable events with ``seq`` strictly greater
        than ``seq``, ordered deterministically by ``seq`` ASC.

        This is the read-only basis for SSE resume / new-event detection. It
        delegates to the authoritative repository's ``iter_after_seq`` and never
        mutates durable state, checkpoints, or projections.

        Note:
            This unbounded variant is retained for service-layer unit tests and
            simple callers. The SSE streaming tail uses the bounded
            :meth:`events_after_seq_bounded` so each read is a DB-bounded batch.

        Args:
            seq: the last durable ``seq`` the client has seen (``Last-Event-ID``).

        Returns:
            A list of ``{"seq": int, "event": {...}}`` dicts in seq order.

        Raises:
            ReadDependencyUnavailableError: authoritative read dependency
                unavailable (HTTP 503).
        """
        try:
            pairs = self._events.iter_after_seq(int(seq))
        except ReadDependencyUnavailableError:
            raise
        except sqlalchemy.exc.SQLAlchemyError as exc:
            raise ReadDependencyUnavailableError(
                "authoritative event store unavailable"
            ) from exc
        return [
            {"seq": int(s), "event": _event_to_dict(e)} for s, e in pairs
        ]

    def events_after_seq_bounded(
        self, seq: int, limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Return at most ``limit`` durable events with ``seq`` strictly greater
        than ``seq``, in ``seq`` order — a DB-bounded tail batch (WO-037-04).

        This is the bounded operator-layer read used by the SSE streaming tail
        so that a burst of events never materialises the whole post-cursor log
        in memory. It delegates to the authoritative WO-037-01 keyset
        ``query_events(cursor=seq, limit=limit)``, which applies a SQL-level
        ``LIMIT`` on the authoritative durable table — no second event store,
        no pagination architecture added to durable core.

        Each returned ``seq`` is the REAL authoritative durable ``seq`` read
        from the authoritative repository metadata (``get_durable_event``
        returns the persisted ``(seq, Event)`` pair), NOT reconstructed as
        ``base + list-index``. The SSE ``id`` therefore always belongs to the
        concrete durable event it labels, exactly as the authoritative log
        stored it — correct even if the durable sequence ever contained gaps
        (e.g. an idempotent duplicate-save rollback).

        Args:
            seq: last durable ``seq`` already emitted (exclusive lower bound).
            limit: maximum batch size; clamped to the repository bounded max.

        Returns:
            A list of at most ``limit`` ``{"seq": int, "event": {...}}`` dicts
            in ascending authoritative ``seq`` order.

        Raises:
            ReadDependencyUnavailableError: authoritative read dependency
                unavailable (HTTP 503).
        """
        try:
            events, _next_cursor = self._events.query_events(
                cursor=int(seq), limit=int(limit)
            )
            pairs = []
            for e in events:
                result = self._events.get_durable_event(e.event_id)
                if result is None:
                    # The event came from the authoritative log a moment ago;
                    # its durable row must still exist. A None here is a data
                    # inconsistency, not a dependency failure — surface it as an
                    # unexpected internal error (500), never as a fake 503.
                    raise RuntimeError(
                        f"durable event {e.event_id!r} vanished between reads"
                    )
                pairs.append((int(result[0]), result[1]))
        except ReadDependencyUnavailableError:
            raise
        except sqlalchemy.exc.SQLAlchemyError as exc:
            raise ReadDependencyUnavailableError(
                "authoritative event store unavailable"
            ) from exc
        return [
            {"seq": int(s), "event": _event_to_dict(ev)} for s, ev in pairs
        ]

    def latest_events(self, limit: int = 50) -> Dict[str, Any]:
        """Return the most recent authoritative durable events (initial SSE
        snapshot) as a deterministic ``{events, next_cursor}`` page.

        Read-only; delegates to ``query_events`` with a bounded ``limit``.
        ``limit`` is clamped to the repository's bounded maximum.
        """
        return self.list_events(limit=limit)

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
