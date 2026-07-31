"""
Signal Reference Plugin.

Reference implementation for Plugin SDK validation.
This is NOT a Signal integration - no signal-cli, no external dependencies.

Purpose:
- Validate Plugin SDK functionality
- Test plugin lifecycle (register, publish, subscribe, shutdown)
- Verify EventBus integration
- Verify Pipeline integration
- Verify Repository integration

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.contracts.plugin import IPlugin
from app.core.event_result import EventResult

logger = logging.getLogger(__name__)


class SignalReferencePlugin(IPlugin):
    """
    Reference plugin for SDK validation.

    This plugin demonstrates proper plugin implementation and
    validates the complete plugin integration without external dependencies.

    Lifecycle:
    1. register() - Initialize and register with EventBus
    2. Startup - Subscribe to events
    3. Run - Publish and receive events
    4. Shutdown - Clean up gracefully

    Attributes:
        _plugin_id: Unique plugin identifier.
        _plugin_name: Human-readable name.
        _version: Plugin version.
        _enabled: Whether plugin is enabled.
        _subscribed_events: Events this plugin subscribes to.
        _published_events: Events this plugin has published.
        _received_events: Events this plugin has received.
        _lock: Thread safety lock.
    """

    def __init__(
        self,
        plugin_id: Optional[str] = None,
        plugin_name: Optional[str] = None,
    ) -> None:
        """
        Initialize the Signal Reference Plugin.

        Args:
            plugin_id: Optional custom plugin ID.
            plugin_name: Optional custom plugin name.
        """
        self._plugin_id = plugin_id or "signal-reference-plugin"
        self._plugin_name = plugin_name or "Signal Reference Plugin"
        self._version = "1.0.0"
        self._description = "Reference plugin for SDK validation"

        self._enabled = True
        self._event_bus = None
        self._event_engine = None
        self._repository = None

        self._subscribed_events: List[str] = ["reference.test"]
        self._published_events: List[Dict[str, Any]] = []
        self._received_events: List[Dict[str, Any]] = []

        self._lock = threading.RLock()
        self._running = False
        self._test_event_id: Optional[str] = None

        logger.info(
            f"SignalReferencePlugin initialized",
            extra={"plugin_id": self._plugin_id}
        )

    @property
    def plugin_id(self) -> str:
        """Get unique plugin identifier."""
        return self._plugin_id

    @property
    def plugin_name(self) -> str:
        """Get human-readable plugin name."""
        return self._plugin_name

    @property
    def version(self) -> str:
        """Get plugin version."""
        return self._version

    @property
    def description(self) -> str:
        """Get plugin description."""
        return self._description

    @property
    def dependencies(self) -> List[str]:
        """Get list of plugin dependencies."""
        return []

    def set_event_bus(self, event_bus: Any) -> None:
        """Set the event bus for pub/sub."""
        with self._lock:
            self._event_bus = event_bus

    def set_event_engine(self, event_engine: Any) -> None:
        """Set the event engine for publishing."""
        with self._lock:
            self._event_engine = event_engine

    def set_repository(self, repository: Any) -> None:
        """Set the repository for persistence."""
        with self._lock:
            self._repository = repository

    def register(self) -> None:
        """
        Called when plugin is registered.

        Initializes plugin state and prepares for operation.
        """
        with self._lock:
            logger.info(
                f"Registering plugin: {self._plugin_id}",
                extra={"plugin_name": self._plugin_name}
            )
            self._enabled = True
            self._running = False

    def unregister(self) -> None:
        """
        Called when plugin is unregistered.

        Performs cleanup and releases resources.
        """
        with self._lock:
            logger.info(f"Unregistering plugin: {self._plugin_id}")

            # Unsubscribe from events
            if self._event_bus and self._running:
                try:
                    self._event_bus.unsubscribe(self._plugin_id)
                except Exception as e:
                    logger.error(f"Error unsubscribing: {e}")

            self._enabled = False
            self._running = False

            # Clear event lists
            self._published_events.clear()
            self._received_events.clear()

    def on_startup(self) -> None:
        """
        Called when application starts.

        Subscribes to reference events and prepares for operation.
        """
        with self._lock:
            if not self._enabled:
                logger.warning(f"Plugin {self._plugin_id} is disabled")
                return

            logger.info(f"Starting plugin: {self._plugin_id}")

            # Subscribe to reference events
            if self._event_bus:
                try:
                    self._event_bus.subscribe(
                        subscriber_id=self._plugin_id,
                        handler=self._handle_event,
                        event_types=["reference.test"],
                    )
                    logger.info(f"Subscribed to: reference.test")
                except Exception as e:
                    logger.error(f"Subscribe error: {e}")

            self._running = True

    def on_shutdown(self) -> None:
        """
        Called when application shuts down.

        Performs graceful shutdown with no orphan threads.
        """
        with self._lock:
            logger.info(f"Shutting down plugin: {self._plugin_id}")

            # Stop accepting new events
            self._running = False

            # Perform final cleanup
            self._published_events.clear()
            self._received_events.clear()

            logger.info(
                f"Plugin shutdown complete: {self._plugin_id}",
                extra={
                    "published_count": len(self._published_events),
                    "received_count": len(self._received_events),
                }
            )

    def _handle_event(self, event: Any, context: Any) -> None:
        """
        Handle received events.

        Args:
            event: The event data.
            context: Event context.
        """
        with self._lock:
            if not self._running:
                return

            event_info = {
                "event_id": str(getattr(event, 'id', uuid.uuid4())),
                "received_at": datetime.now(timezone.utc).isoformat(),
                "source": getattr(context, 'source', 'unknown') if context else 'unknown',
            }
            self._received_events.append(event_info)

            logger.debug(
                f"Event received: {event_info['event_id']}",
                extra={"event": event_info}
            )

    def publish_test_event(self) -> Optional[str]:
        """
        Publish a test event through the Event Engine.

        Returns:
            The published event ID or None if failed.
        """
        with self._lock:
            if not self._running or not self._event_engine:
                logger.warning("Cannot publish: plugin not running or no engine")
                return None

            event_id = uuid.uuid4()

            event_data = {
                "id": str(event_id),
                "title": "Signal Reference Test Event",
                "source": self._plugin_id,
                "source_type": "PLUGIN",
                "category": "reference.test",
                "priority": "NORMAL",
                "status": "NEW",
                "message": "This is a test event from SignalReferencePlugin",
                "event_time": datetime.now(timezone.utc).isoformat(),
                "correlation_id": f"test-{event_id}",
            }

            try:
                # Publish through Event Engine (pipeline)
                result = self._event_engine.publish(event_data)

                if result.success:
                    self._test_event_id = str(event_id)
                    self._published_events.append({
                        "event_id": str(event_id),
                        "published_at": datetime.now(timezone.utc).isoformat(),
                        "success": True,
                    })
                    logger.info(f"Test event published: {event_id}")
                    return str(event_id)
                else:
                    self._published_events.append({
                        "event_id": str(event_id),
                        "published_at": datetime.now(timezone.utc).isoformat(),
                        "success": False,
                        "errors": result.errors,
                    })
                    logger.error(f"Test event publish failed: {result.errors}")
                    return None

            except Exception as e:
                logger.error(f"Publish error: {e}")
                return None

    def validate_lifecycle(self) -> Dict[str, Any]:
        """
        Validate the complete plugin lifecycle.

        Returns:
            Dictionary with validation results.
        """
        with self._lock:
            published_count = len(self._published_events)
            received_count = len(self._received_events)

            # Check for test event in received (from EventBus)
            test_event_received = any(
                e["event_id"] == self._test_event_id
                for e in self._received_events
            )

            return {
                "plugin_id": self._plugin_id,
                "registered": True,
                "enabled": self._enabled,
                "running": self._running,
                "published_count": published_count,
                "received_count": received_count,
                "test_event_received": test_event_received,
                "lifecycle_valid": (
                    published_count > 0 and
                    self._running and
                    self._enabled
                ),
            }

    def get_status(self) -> Dict[str, Any]:
        """Get current plugin status."""
        with self._lock:
            return {
                "plugin_id": self._plugin_id,
                "plugin_name": self._plugin_name,
                "version": self._version,
                "enabled": self._enabled,
                "running": self._running,
                "published_events": len(self._published_events),
                "received_events": len(self._received_events),
                "subscriptions": self._subscribed_events,
            }
