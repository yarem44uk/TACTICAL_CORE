"""WO-016 — Deterministic Event -> Durable Relation projection bridge.

Translates a canonical ``app.event.event.Event`` into a durable relation
projection via the existing ``IRelationRepository`` / durable repository
implementation.

Architectural contract (Durable Relation Projection):
  * This is a thin, deterministic projection adapter, downstream of the
    canonical Entity/Event projection.  It does NOT introduce an independent
    event-dispatch plane, a second database/session owner, a second EventBus,
    or a second EventPipeline.
  * It uses the existing durable relation repository (single
    ``DatabaseSessionManager`` owner) and the deterministic relation identity
    ``deterministic_relation_id(source, target, relation_type)``.
  * It is best-effort (mirrors ``EntityBridge``): errors are caught, logged
    and swallowed so a failing relation projection can never roll back or
    prevent the already-durable canonical Event persistence.
  * It never invents entity identity and never auto-creates entities: it only
    persists a relation when the canonical Event carries a usable
    ``source_entity_id``, ``target_entity_id`` and ``relation_type``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional
from uuid import UUID

from app.entity_relations.sqlalchemy_relation_repository import (
    SQLAlchemyRelationRepository,
    deterministic_relation_id,
)
from app.entity_relations.interfaces.i_relation_repository import IRelationRepository

logger = logging.getLogger(__name__)


class RelationProjection:
    """Deterministic canonical ``Event`` -> durable Relation projection.

    The projection extracts relation fields from a canonical Event and
    persists them through the authoritative ``IRelationRepository`` (the
    durable SQLAlchemy implementation) under a deterministic relation id.

    Best-effort by design: a projection failure is logged and swallowed, so
    it never interrupts the EventPipeline or rolls back the already-durable
    canonical Event.
    """

    def __init__(self, repository: Optional[IRelationRepository] = None) -> None:
        self._repository: IRelationRepository = (
            repository or SQLAlchemyRelationRepository()
        )

    def process_event(
        self,
        *,
        event_id: str | int | None,
        source_entity_id: str | UUID | None,
        target_entity_id: str | UUID | None,
        relation_type: Optional[str],
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Project a single relation from a canonical Event.

        Returns the deterministic durable ``relation_id`` if a relation was
        persisted, or ``None`` if the Event carried no usable relation
        (deterministic skip — never invents an identity, never auto-creates
        entities).

        Best-effort: exceptions are caught, logged and swallowed.
        """
        if not source_entity_id or not target_entity_id or not relation_type:
            logger.debug(
                "RelationProjection skipped (missing source/target/type). "
                "event_id=%s",
                event_id,
            )
            return None

        try:
            relation_id = deterministic_relation_id(
                source_entity_id, target_entity_id, relation_type
            )
            self._repository.save(
                {
                    "relation_id": relation_id,
                    "source_entity_id": str(source_entity_id),
                    "target_entity_id": str(target_entity_id),
                    "relation_type": str(relation_type),
                    "confidence": float(confidence),
                    "source_event_id": (
                        str(event_id) if event_id is not None else None
                    ),
                    "metadata": dict(metadata or {}),
                }
            )
            logger.info(
                "Relation projected: source=%s target=%s type=%s event=%s",
                source_entity_id,
                target_entity_id,
                relation_type,
                event_id,
            )
            return relation_id
        except Exception:  # noqa: BLE001 - best-effort by design
            logger.exception(
                "RelationProjection failed (best-effort, not propagating). "
                "event_id=%s source=%s target=%s type=%s",
                event_id,
                source_entity_id,
                target_entity_id,
                relation_type,
            )
            return None


def project_relation_from_event(
    repository: Optional[IRelationRepository] = None,
) -> Callable[[Any], None]:
    """Return a deterministic canonical ``Event`` -> relation projection callable.

    The returned callable adapts a canonical ``app.event.event.Event`` into
    ``RelationProjection.process_event``.  The convention mirrors the Entity
    projection: the relation subject is the canonical ``Event.entity_id`` and
    the relation target/type are read deterministically from ``Event.payload``:

        source_entity_id = Event.entity_id
        target_entity_id = Event.payload["target_entity_id"]
                           or Event.payload["related_entity_id"]
        relation_type    = Event.payload["relation_type"]

    Only a relation is produced when BOTH source and target entity ids are
    present AND ``relation_type`` is a non-empty string — otherwise it is
    skipped deterministically (no invented identity, no auto entity creation).

    Best-effort: a projection failure is swallowed, so it can never roll back
    or prevent the already-durable canonical Event.
    """
    projection = RelationProjection(repository=repository)

    def project(event: Any) -> None:
        payload = dict(getattr(event, "payload", None) or {})
        source_entity_id = getattr(event, "entity_id", None)
        target_entity_id = payload.get("target_entity_id") or payload.get(
            "related_entity_id"
        )
        relation_type = payload.get("relation_type")
        metadata = payload.get("relation_metadata") or {}
        projection.process_event(
            event_id=getattr(event, "event_id", None),
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relation_type=relation_type,
            confidence=float(payload.get("confidence", 1.0)),
            metadata=metadata if isinstance(metadata, dict) else {},
        )

    return project
