"""WO-014-024 — Canonical Entity Read-Side (thin read-only facade).

Provides a canonical, production-wired, read-only surface over the
authoritative :class:`IEntityManager` for downstream consumers that need to
query the derived Entity state.

Architectural contract:
  * The read-side is STRICTLY read-only.  It exposes ``get``, ``get_by_type``
    and ``list`` only.  It NEVER mutates Entity state and NEVER performs
    projection.
  * It delegates to the existing :class:`IEntityManager` (the authoritative
    Entity owner).  No second Entity store, no second persistence plane, no
    second database/session owner is introduced.
  * ``EntityManager`` remains the authoritative owner of Entity state
    mutation/persistence; this facade only reads through it.
  * Query results are deterministic.

Entity identity: ``Entity.id`` (``entity_id``).  This is DISTINCT from the
canonical Event identity (``Event.event_id``) and from any SQL surrogate key.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from app.entity_manager.interfaces.i_entity_manager import IEntityManager


class EntityReadService:
    """Thin, read-only facade over the authoritative EntityManager.

    Exposes the canonical downstream read surface for the derived Entity
    state produced by the Event -> Entity projection.
    """

    def __init__(self, entity_manager: IEntityManager) -> None:
        if entity_manager is None:
            raise ValueError("entity_manager is required")
        self._entity_manager = entity_manager

    # ------------------------------------------------------------------
    # Read API (read-only; no mutation, no projection)
    # ------------------------------------------------------------------

    def get(
        self,
        entity_id: UUID | str,
        entity_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return a single Entity by its identity.

        Args:
            entity_id: The Entity identity (``Entity.id``).
            entity_type: Optional Entity type filter.  When provided, only an
                Entity of exactly this type is returned; otherwise the unique
                Entity carrying ``entity_id`` is returned.

        Returns:
            The Entity state dict, or ``None`` if no Entity matches.
        """
        if entity_type is not None:
            return self._entity_manager.get_entity(str(entity_type), entity_id)

        target = str(entity_id)
        for entity in self._entity_manager.list_entities():
            if str(entity.get("entity_id")) == target:
                return entity
        return None

    def get_by_type(self, entity_type: str) -> List[Dict[str, Any]]:
        """Return all Entities of a given Entity type (deterministic)."""
        return self._entity_manager.list_entities(str(entity_type))

    def list(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """List persisted Entities, optionally filtered by Entity type."""
        return self._entity_manager.list_entities(
            str(entity_type) if entity_type is not None else None
        )
