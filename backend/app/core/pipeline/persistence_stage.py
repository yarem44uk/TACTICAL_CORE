"""
Persistence Stage.

Persists event to database.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.core.pipeline.base_stage import BaseStage
from app.core.pipeline.context import PipelineContext

logger = logging.getLogger(__name__)


class PersistenceStage(BaseStage):
    """
    Persists event to database.

    Optionally delegates persisted events to an EntityBridge for
    entity-layer updates.  EntityBridge is best-effort: errors are
    logged but never propagate and never affect persistence.
    """

    def __init__(
        self,
        repository: Optional[Any] = None,
        session: Optional[Any] = None,
        entity_bridge: Optional[Any] = None,
        **kwargs,
    ) -> None:
        """
        Initialize the persistence stage.

        Args:
            repository: Database repository for event persistence.
            session: Database session for commit / rollback.
            entity_bridge: Optional EntityBridge for entity updates.
        """
        super().__init__(name="persistence", order=50, required=True, **kwargs)
        self._repository = repository
        self._session = session
        self._entity_bridge = entity_bridge

    def set_repository(self, repository: Any) -> None:
        """Set the event repository."""
        self._repository = repository

    def set_session(self, session: Any) -> None:
        """Set the database session."""
        self._session = session

    def set_entity_bridge(self, entity_bridge: Any) -> None:
        """
        Set the EntityBridge for entity updates.

        Args:
            entity_bridge: An IEntityBridge implementation (optional).
        """
        self._entity_bridge = entity_bridge

    def _execute(self, context: PipelineContext) -> Optional[Dict[str, Any]]:
        """Persist event to database."""
        if self._repository is None:
            context.stage_warnings["persistence"] = [{"message": "No repository configured"}]
            return None

        try:
            event = self._repository.create(**context.event_data)
            if self._session is not None:
                self._session.commit()
            context.metadata["persisted_id"] = str(context.event_id)
            context.metadata["database_saved"] = True

            # Best-effort entity bridge — must not break persistence
            self._invoke_entity_bridge(context)

            return context.event_data
        except Exception as e:
            context.stage_errors["persistence"] = [{"code": "PERSISTENCE_ERROR", "message": str(e)}]
            if self._session is not None:
                self._session.rollback()
            return None

    def _invoke_entity_bridge(self, context: PipelineContext) -> None:
        """
        Delegate to EntityBridge (best-effort).

        Errors are logged but never propagated.  This method must not
        raise exceptions — the bridge must not disrupt the pipeline.

        Args:
            context: The current pipeline context with event data.
        """
        if self._entity_bridge is None:
            return

        try:
            self._entity_bridge.process_event(
                event_data=context.event_data,
                event_id=str(context.event_id),
                correlation_id=context.correlation_id,
            )
            logger.debug(
                "EntityBridge processed event: event_id=%s",
                context.event_id,
            )
        except Exception:
            # Best-effort: log and swallow — never break pipeline
            logger.exception(
                "EntityBridge failed for event_id=%s (best-effort, not propagating).",
                context.event_id,
            )
