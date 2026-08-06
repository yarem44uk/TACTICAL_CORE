"""
EntityBridge Module.

Translates pipeline events into entity update requests and delegates
them to an :class:`IEntityManager` implementation.

This module has **zero** dependencies on:

- SQLAlchemy
- Database sessions
- Repository layer
- Plugin SDK
- Intelligence domain models

It depends exclusively on ``IEntityManager``.

Author: Tactical Core Engineering Team
Version: 1.0
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from .interfaces import EntityUpdateRequest, IEntityBridge, IEntityManager

logger = logging.getLogger(__name__)


class EntityBridge(IEntityBridge):
    """
    Bridge between the event pipeline and the entity management layer.

    Responsibilities:
    1. Receive raw event data from the pipeline.
    2. Determine which entity(ies) the event affects.
    3. Build :class:`EntityUpdateRequest` objects.
    4. Delegate to :class:`IEntityManager.apply_update`.

    All operations are **best-effort**: errors are logged but never
    propagated.  A failing bridge must NOT break the pipeline.
    """

    def __init__(self, entity_manager: IEntityManager) -> None:
        """
        Initialize the bridge with an entity manager.

        Args:
            entity_manager: The entity manager to delegate updates to.
                            Must implement :class:`IEntityManager`.
        """
        self._entity_manager = entity_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_event(
        self,
        event_data: Dict[str, Any],
        event_id: str | int | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """
        Process a single pipeline event and apply entity updates.

        Best-effort: exceptions are caught, logged, and swallowed.
        The pipeline is never interrupted.

        Args:
            event_data: Parsed event payload from the pipeline.
            event_id: Optional pipeline event identifier for correlation.
            correlation_id: Optional trace correlation ID.
        """
        try:
            requests = self._build_requests(event_data, event_id, correlation_id)
            for request in requests:
                self._apply_request(request)
        except Exception:
            logger.exception(
                "EntityBridge.process_event failed (best-effort, not propagating). "
                "event_id=%s correlation_id=%s",
                event_id,
                correlation_id,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_requests(
        self,
        event_data: Dict[str, Any],
        event_id: Optional[str],
        correlation_id: Optional[str],
    ) -> List[EntityUpdateRequest]:
        """
        Translate raw event data into one or more update requests.

        Current heuristic (may be extended by subclass / plugin):

        - If ``entity_type`` and ``entity_id`` are present in event_data,
          treat the payload as an entity update.
        - Otherwise produce no requests (log a debug message).

        Args:
            event_data: The raw event dict.
            event_id: Pipeline event ID for correlation.
            correlation_id: Trace correlation ID.

        Returns:
            List of :class:`EntityUpdateRequest` objects.
        """
        entity_type: Optional[str] = event_data.get("entity_type")
        entity_id: Optional[str] = event_data.get("entity_id")

        if not entity_type or not entity_id:
            logger.debug(
                "Event does not contain entity_type/entity_id — skipping bridge. "
                "event_id=%s",
                event_id,
            )
            return []

        # Extract the entity payload — nested under "entity" if present,
        # otherwise use the remaining event_data keys.
        updates = event_data.get("entity", event_data.copy())

        request = EntityUpdateRequest(
            entity_type=entity_type,
            entity_id=entity_id,
            updates=updates,
            source_event_id=event_id,
            correlation_id=correlation_id,
        )

        logger.info(
            "EntityBridge built update request: entity_type=%s entity_id=%s",
            entity_type,
            entity_id,
        )

        return [request]

    def _apply_request(self, request: EntityUpdateRequest) -> None:
        """
        Delegate a single update request to the entity manager.

        Catches and logs any exception without propagating.

        Args:
            request: The structured update request.
        """
        try:
            success = self._entity_manager.apply_update(
                **request.to_entity_manager_params()
            )
            if success:
                logger.info(
                    "EntityBridge applied update: entity_type=%s entity_id=%s request_id=%s",
                    request.entity_type,
                    request.entity_id,
                    request.request_id,
                )
            else:
                logger.warning(
                    "EntityBridge apply_update returned False: entity_type=%s entity_id=%s",
                    request.entity_type,
                    request.entity_id,
                )
        except Exception:
            logger.exception(
                "EntityBridge._apply_request failed for entity_type=%s entity_id=%s",
                request.entity_type,
                request.entity_id,
            )
