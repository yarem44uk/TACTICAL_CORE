"""
Persistence Stage.

Persists event to database.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from typing import Any, Dict, Optional

from app.core.pipeline.base_stage import BaseStage
from app.core.pipeline.context import PipelineContext


class PersistenceStage(BaseStage):
    """
    Persists event to database.
    """

    def __init__(
        self,
        repository: Optional[Any] = None,
        session: Optional[Any] = None,
        **kwargs
    ) -> None:
        super().__init__(name="persistence", order=50, required=True, **kwargs)
        self._repository = repository
        self._session = session

    def set_repository(self, repository: Any) -> None:
        """Set the event repository."""
        self._repository = repository

    def set_session(self, session: Any) -> None:
        """Set the database session."""
        self._session = session

    def _execute(self, context: PipelineContext) -> Optional[Dict[str, Any]]:
        """Persist event to database."""
        if self._repository is None or self._session is None:
            context.stage_warnings["persistence"] = [{"message": "No database configured"}]
            return None

        try:
            event = self._repository.create(**context.event_data)
            self._session.commit()
            context.metadata["persisted_id"] = str(context.event_id)
            context.metadata["database_saved"] = True
            return context.event_data
        except Exception as e:
            context.stage_errors["persistence"] = [{"code": "PERSISTENCE_ERROR", "message": str(e)}]
            self._session.rollback()
            return None
