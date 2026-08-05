"""
Plugin Event Dispatcher.

Bridge between PluginContext and PipelineDispatcher.
Plugins emit events through this dispatcher, which routes them into
the central Pipeline and ultimately to EventPersistenceService.

Architecture Rule:
No plugin may access Repository, Database, or SQLAlchemy directly.
All plugin events MUST flow through PluginEventDispatcher.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from typing import Any, Dict, Optional

from app.pipeline_dispatcher.dispatcher import PipelineDispatcher

logger = logging.getLogger(__name__)


class PluginEventDispatcher:
    """
    Plugin-facing event dispatcher.

    Plugins use this to emit events into the central pipeline.
    It translates plugin-specific data into Pipeline-compatible format
    and delegates to PipelineDispatcher.

    Usage:
        dispatcher = PluginEventDispatcher(
            pipeline_dispatcher=core_dispatcher,
            plugin_id="signal",
        )
        event_id = dispatcher.emit({
            "event_type": "signal.message",
            "title": "Incoming Signal",
            "payload": {"from": "+380..."},
        })
    """

    def __init__(
        self,
        pipeline_dispatcher: PipelineDispatcher,
        plugin_id: str,
    ) -> None:
        """
        Initialize the plugin event dispatcher.

        Args:
            pipeline_dispatcher: The core PipelineDispatcher instance.
            plugin_id: Identifier of the plugin that owns this dispatcher.
        """
        self._pipeline_dispatcher = pipeline_dispatcher
        self._plugin_id = plugin_id

    @property
    def plugin_id(self) -> str:
        """Get the plugin identifier."""
        return self._plugin_id

    def emit(
        self,
        event_data: Dict[str, Any],
        source: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> Optional[str]:
        """
        Emit a single event into the pipeline.

        Args:
            event_data: Event data dictionary with event_type, title, etc.
            source: Optional source identifier (defaults to plugin_id).
            source_type: Optional source type (defaults to "plugin").

        Returns:
            Event ID string if dispatched successfully, None otherwise.
        """
        effective_source = source or self._plugin_id
        effective_source_type = source_type or "plugin"

        event_id = self._pipeline_dispatcher.dispatch(
            event_data=event_data,
            plugin=self._plugin_id,
            source=effective_source,
            source_type=effective_source_type,
        )

        if event_id:
            logger.debug(
                f"PluginEventDispatcher: plugin {self._plugin_id} "
                f"emitted event {event_id}"
            )
        else:
            logger.error(
                f"PluginEventDispatcher: plugin {self._plugin_id} "
                f"failed to emit event"
            )

        return event_id

    def emit_batch(
        self,
        events: list[Dict[str, Any]],
        source: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> list[str]:
        """
        Emit multiple events into the pipeline.

        Args:
            events: List of event data dictionaries.
            source: Optional source identifier.
            source_type: Optional source type.

        Returns:
            List of successfully dispatched event IDs.
        """
        dispatched = []
        for event_data in events:
            event_id = self.emit(event_data, source=source, source_type=source_type)
            if event_id:
                dispatched.append(event_id)
        return dispatched
