"""
Broadcast Stage.

Broadcasts event via WebSocket.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from typing import Any, Dict, Optional

from app.core.pipeline.base_stage import BaseStage
from app.core.pipeline.context import PipelineContext


class BroadcastStage(BaseStage):
    """
    Broadcasts event via WebSocket to connected clients.
    """

    def __init__(self, broadcaster: Optional[Any] = None, **kwargs) -> None:
        super().__init__(name="broadcast", order=85, required=False, **kwargs)
        self._broadcaster = broadcaster

    def set_broadcaster(self, broadcaster: Any) -> None:
        """Set the WebSocket broadcaster."""
        self._broadcaster = broadcaster

    def _execute(self, context: PipelineContext) -> Optional[Dict[str, Any]]:
        """Broadcast event."""
        if self._broadcaster is None:
            return None

        try:
            self._broadcaster(context.event_data, context.metadata)
            context.metadata["broadcast_sent"] = True
        except Exception as e:
            context.stage_errors["broadcast"] = [{"code": "BROADCAST_ERROR", "message": str(e)}]

        return None
