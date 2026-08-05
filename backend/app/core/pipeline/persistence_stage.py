"""
Persistence Stage.

Persists event to database via EventPersistenceService.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from typing import Any, Dict, Optional

from app.core.pipeline.base_stage import BaseStage
from app.core.pipeline.context import PipelineContext
from app.database import EventPersistenceService


class PersistenceStage(BaseStage):
    """
    Persists event to database.
    """

    def __init__(
        self,
        persistence_service: Optional[EventPersistenceService] = None,
        repository: Optional[Any] = None,
        session: Optional[Any] = None,
        **kwargs
    ) -> None:
        super().__init__(name="persistence", order=50, required=True, **kwargs)
        self._persistence_service = persistence_service
        self._repository = repository
        self._session = session

    def set_persistence_service(
        self, persistence_service: EventPersistenceService
    ) -> None:
        """Set the event persistence service."""
        self._persistence_service = persistence_service

    def set_repository(self, repository: Any) -> None:
        """Set the event repository (legacy)."""
        self._repository = repository

    def set_session(self, session: Any) -> None:
        """Set the database session (legacy)."""
        self._session = session

    def _execute(self, context: PipelineContext) -> Optional[Dict[str, Any]]:
        """Persist event to database."""
        # Prefer persistence_service (WO-010-003-R2 architecture)
        if self._persistence_service is not None:
            return self._execute_with_service(context)
        # Fallback to direct repository (backward compatible)
        if self._repository is None:
            context.stage_warnings["persistence"] = [
                {"message": "No persistence service or repository configured"}
            ]
            return None
        return self._execute_with_repository(context)

    def _execute_with_service(
        self, context: PipelineContext
    ) -> Optional[Dict[str, Any]]:
        """Persist via EventPersistenceService."""
        try:
            event_id = self._persistence_service.create_event(context.event_data)
            if event_id is None:
                context.stage_errors["persistence"] = [
                    {"code": "PERSISTENCE_ERROR", "message": "Event creation failed"}
                ]
                return None
            context.metadata["persisted_id"] = event_id
            context.metadata["database_saved"] = True
            return context.event_data
        except Exception as e:
            context.stage_errors["persistence"] = [
                {"code": "PERSISTENCE_ERROR", "message": str(e)}
            ]
            return None

    def _execute_with_repository(
        self, context: PipelineContext
    ) -> Optional[Dict[str, Any]]:
        """Persist via direct repository.

        DEPRECATED: This path exists only for backward compatibility.
        New code must use EventPersistenceService via the persistence_service
        parameter. This method will be removed in a future major release.
        """
        try:
            # Ensure event_data carries the pipeline-generated event_id
            data = dict(context.event_data)
            if "id" not in data:
                data["id"] = str(context.event_id)
            event = self._repository.create(**data)
            if self._session is not None:
                self._session.commit()
            persisted_id = str(context.event_id)
            if hasattr(event, "id") and event.id is not None:
                persisted_id = str(event.id)
            context.metadata["persisted_id"] = persisted_id
            context.metadata["database_saved"] = True
            return context.event_data
        except Exception as e:
            context.stage_errors["persistence"] = [
                {"code": "PERSISTENCE_ERROR", "message": str(e)}
            ]
            if self._session is not None:
                self._session.rollback()
            return None
