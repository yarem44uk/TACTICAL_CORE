"""
AI Stage.

Notifies AI engine about events for analysis.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from typing import Any, Dict, Optional

from app.core.pipeline.base_stage import BaseStage
from app.core.pipeline.context import PipelineContext


class AIStage(BaseStage):
    """
    Sends events to AI engine for analysis.
    """

    def __init__(self, ai_notifier: Optional[Any] = None, **kwargs) -> None:
        super().__init__(name="ai", order=92, required=False, **kwargs)
        self._ai_notifier = ai_notifier

    def set_ai_notifier(self, ai_notifier: Any) -> None:
        """Set the AI notifier."""
        self._ai_notifier = ai_notifier

    def can_execute(self, context: PipelineContext) -> bool:
        """Only process if AI is enabled."""
        if not self._enabled:
            return False
        ai_enabled = context.event_data.get("metadata", {}).get("ai_enabled", True)
        return ai_enabled and not context.cancelled

    def _execute(self, context: PipelineContext) -> Optional[Dict[str, Any]]:
        """Notify AI engine."""
        if self._ai_notifier is None:
            return None

        try:
            self._ai_notifier(context.event_data, context.metadata)
            context.metadata["ai_notified"] = True
        except Exception as e:
            context.stage_errors["ai"] = [{"code": "AI_ERROR", "message": str(e)}]

        return None
