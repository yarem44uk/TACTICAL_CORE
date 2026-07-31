"""
History Stage.

Stores event in history for replay and search.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from typing import Any, Dict, Optional

from app.core.pipeline.base_stage import BaseStage
from app.core.pipeline.context import PipelineContext


class HistoryStage(BaseStage):
    """
    Stores event in history buffer.
    """

    def __init__(self, history_manager: Optional[Any] = None, **kwargs) -> None:
        super().__init__(name="history", order=80, required=False, **kwargs)
        self._history = history_manager

    def set_history_manager(self, history_manager: Any) -> None:
        """Set the history manager."""
        self._history = history_manager

    def _execute(self, context: PipelineContext) -> Optional[Dict[str, Any]]:
        """Store event in history."""
        if self._history is None:
            self._add_warning(context, "No history manager configured")
            return None

        try:
            self._history.add(
                event_id=context.event_id,
                event_type=context.event_data.get("category", "unknown"),
                event=context.event_data,
                context=context.metadata,
                result=None,
            )
        except Exception as e:
            context.stage_errors["history"] = [{"code": "HISTORY_ERROR", "message": str(e)}]

        return None

    def _add_warning(self, context: PipelineContext, message: str) -> None:
        """Add a warning to context."""
        warnings = dict(context.stage_warnings)
        warnings.setdefault("history", []).append({"message": message})
