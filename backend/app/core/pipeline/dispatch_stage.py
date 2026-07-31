"""
Dispatch Stage.

Dispatches event to registered subscribers.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from typing import Any, Dict, Optional

from app.core.pipeline.base_stage import BaseStage
from app.core.pipeline.context import PipelineContext


class DispatchStage(BaseStage):
    """
    Dispatches event to subscribers.
    """

    def __init__(
        self,
        dispatcher: Optional[Any] = None,
        registry: Optional[Any] = None,
        **kwargs
    ) -> None:
        super().__init__(name="dispatch", order=90, required=False, **kwargs)
        self._dispatcher = dispatcher
        self._registry = registry

    def set_dispatcher(self, dispatcher: Any) -> None:
        """Set the event dispatcher."""
        self._dispatcher = dispatcher

    def set_registry(self, registry: Any) -> None:
        """Set the event registry."""
        self._registry = registry

    def _execute(self, context: PipelineContext) -> Optional[Dict[str, Any]]:
        """Dispatch to subscribers."""
        if self._dispatcher is None:
            return None

        event_type = context.event_data.get("category", "unknown")

        try:
            results = self._dispatcher.dispatch(
                event=context.event_data,
                context=context.metadata,
                event_type=event_type,
            )
            context.metadata["subscribers_notified"] = len(results)
        except Exception as e:
            context.stage_errors["dispatch"] = [{"code": "DISPATCH_ERROR", "message": str(e)}]

        return None
