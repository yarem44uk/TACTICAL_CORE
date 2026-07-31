"""
Plugin Stage.

Notifies registered plugins about events.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from typing import Any, Dict, List, Optional

from app.core.pipeline.base_stage import BaseStage
from app.core.pipeline.context import PipelineContext


class PluginStage(BaseStage):
    """
    Notifies plugins about events.
    """

    def __init__(self, registry: Optional[Any] = None, **kwargs) -> None:
        super().__init__(name="plugins", order=95, required=False, **kwargs)
        self._registry = registry

    def set_registry(self, registry: Any) -> None:
        """Set the event registry."""
        self._registry = registry

    def _execute(self, context: PipelineContext) -> Optional[Dict[str, Any]]:
        """Notify plugins."""
        if self._registry is None:
            return None

        event_type = context.event_data.get("category", "unknown")
        notified: List[str] = []

        try:
            for plugin_id, plugin in self._registry.plugins.items():
                if event_type in plugin.subscriptions:
                    notified.append(plugin_id)

            context.metadata["plugins_notified"] = notified
        except Exception as e:
            context.stage_errors["plugins"] = [{"code": "PLUGIN_ERROR", "message": str(e)}]

        return None
