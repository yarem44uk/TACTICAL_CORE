"""
Plugin Manager Implementation.

Implements IPluginManager interface for plugin lifecycle management.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.contracts.plugin import IPlugin, IPluginManager

logger = logging.getLogger(__name__)


class PluginState:
    """Internal plugin state tracking."""

    DISCOVERED = "DISCOVERED"
    VALIDATED = "VALIDATED"
    LOADED = "LOADED"
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"

    def __init__(
        self,
        plugin: IPlugin,
        enabled: bool = True,
        loaded_at: Optional[datetime] = None,
        error: Optional[str] = None,
    ) -> None:
        self.plugin = plugin
        self.enabled = enabled
        self.loaded_at = loaded_at or datetime.now(timezone.utc)
        self.last_error = error
        self.error_count = 0
        self._state = self.DISCOVERED

    def record_error(self, error: str) -> None:
        """Record an error for this plugin."""
        self.last_error = error
        self.error_count += 1

    def clear_error(self) -> None:
        """Clear the error state."""
        self.last_error = None
        self.error_count = 0


class PluginManager(IPluginManager):
    """
    Plugin Manager implementation.

    Manages plugin lifecycle, registration, and discovery.
    Thread-safe implementation using RLock.

    Lifecycle Order:
        initialize() -> register() -> start() -> publish() -> stop() -> unregister()

    Attributes:
        _registry: Internal plugin registry.
        _lock: Thread safety lock.

    Usage:
        >>> manager = PluginManager()
        >>> manager.register_plugin(my_plugin)
        >>> plugin = manager.get_plugin("my-plugin-id")
        >>> manager.enable_plugin("my-plugin-id")
    """

    def __init__(self) -> None:
        """Initialize the Plugin Manager."""
        self._lock = threading.RLock()
        self._registry: Dict[str, PluginState] = {}
        self._event_bus = None
        self._event_engine = None

        logger.info("PluginManager initialized")

    def set_event_bus(self, event_bus: Any) -> None:
        """Set the event bus for plugin communication."""
        with self._lock:
            self._event_bus = event_bus

    def set_event_engine(self, event_engine: Any) -> None:
        """Set the event engine for plugin communication."""
        with self._lock:
            self._event_engine = event_engine

    def register_plugin(self, plugin: IPlugin) -> None:
        """
        Register a plugin.

        Lifecycle: initialize() -> register() -> start() -> publish() -> stop() -> unregister()

        Args:
            plugin: Plugin instance to register.

        Raises:
            ValueError: If plugin is already registered.
        """
        with self._lock:
            if plugin.plugin_id in self._registry:
                raise ValueError(
                    f"Plugin {plugin.plugin_id} is already registered"
                )

            try:
                # Step 1: Initialize
                if hasattr(plugin, "initialize"):
                    plugin.initialize()

                # Step 2: Register
                plugin.register()

                # Create state after successful registration
                self._registry[plugin.plugin_id] = PluginState(
                    plugin=plugin,
                    enabled=True,
                    loaded_at=datetime.now(timezone.utc),
                )
                self._registry[plugin.plugin_id]._state = PluginState.LOADED

                logger.info(
                    f"Plugin registered: {plugin.plugin_id}",
                    extra={"plugin_name": plugin.plugin_name}
                )
            except Exception as e:
                logger.error(
                    f"Failed to register plugin {plugin.plugin_id}: {e}"
                )
                raise

    def unregister_plugin(self, plugin_id: str) -> bool:
        """
        Unregister a plugin by ID.

        Args:
            plugin_id: Plugin identifier to unregister.

        Returns:
            True if the plugin was unregistered, False if not found.
        """
        with self._lock:
            if plugin_id not in self._registry:
                logger.warning(f"Plugin not found for unregister: {plugin_id}")
                return False

            state = self._registry.get(plugin_id)

            # Check if plugin was registered (has internal state)
            if state is None:
                logger.warning(f"Plugin state not found for unregister: {plugin_id}")
                return False

            try:
                state.plugin.unregister()
                del self._registry[plugin_id]
                logger.info(f"Plugin unregistered: {plugin_id}")
                return True
            except Exception as e:
                logger.error(
                    f"Error during plugin unregister {plugin_id}: {e}"
                )
                # Clean up registry even on error
                if plugin_id in self._registry:
                    del self._registry[plugin_id]
                return False

    def get_plugin(self, plugin_id: str) -> Optional[IPlugin]:
        """
        Get a plugin by ID.

        Args:
            plugin_id: Plugin identifier.

        Returns:
            The plugin instance or None if not found.
        """
        with self._lock:
            state = self._registry.get(plugin_id)
            return state.plugin if state else None

    def list_plugins(self) -> List[IPlugin]:
        """
        List all registered plugins.

        Returns:
            List of all plugin instances.
        """
        with self._lock:
            return [state.plugin for state in self._registry.values()]

    def enable_plugin(self, plugin_id: str) -> bool:
        """
        Enable a plugin.

        Args:
            plugin_id: Plugin identifier to enable.

        Returns:
            True if the plugin was enabled, False if not found.
        """
        with self._lock:
            state = self._registry.get(plugin_id)
            if state is None:
                logger.warning(f"Plugin not found for enable: {plugin_id}")
                return False

            if not state.enabled:
                state.enabled = True
                state.clear_error()
                logger.info(f"Plugin enabled: {plugin_id}")

            return True

    def disable_plugin(self, plugin_id: str) -> bool:
        """
        Disable a plugin.

        Args:
            plugin_id: Plugin identifier to disable.

        Returns:
            True if the plugin was disabled, False if not found.
        """
        with self._lock:
            state = self._registry.get(plugin_id)
            if state is None:
                logger.warning(f"Plugin not found for disable: {plugin_id}")
                return False

            if state.enabled:
                state.enabled = False
                logger.info(f"Plugin disabled: {plugin_id}")

            return True

    def get_plugin_health(self, plugin_id: str) -> Dict[str, Any]:
        """
        Get health status of a plugin.

        Args:
            plugin_id: Plugin identifier.

        Returns:
            Dictionary with health information.
        """
        with self._lock:
            state = self._registry.get(plugin_id)

            if state is None:
                return {
                    "status": "unknown",
                    "plugin_id": plugin_id,
                    "error": "Plugin not found",
                }

            status = "healthy"
            if not state.enabled:
                status = "disabled"
            elif state.last_error:
                status = "unhealthy"

            return {
                "plugin_id": plugin_id,
                "plugin_name": state.plugin.plugin_name,
                "status": status,
                "state": state._state,
                "enabled": state.enabled,
                "version": state.plugin.version,
                "loaded_at": state.loaded_at.isoformat() if state.loaded_at else None,
                "last_error": state.last_error,
                "error_count": state.error_count,
                "description": state.plugin.description,
            }

    def get_all_health(self) -> Dict[str, Any]:
        """
        Get health status of all plugins.

        Returns:
            Dictionary with overall health and per-plugin status.
        """
        with self._lock:
            plugins_health = {}
            healthy = 0
            unhealthy = 0
            disabled = 0

            for plugin_id in self._registry:
                health = self.get_plugin_health(plugin_id)
                plugins_health[plugin_id] = health

                status = health["status"]
                if status == "healthy":
                    healthy += 1
                elif status == "unhealthy":
                    unhealthy += 1
                elif status == "disabled":
                    disabled += 1

            return {
                "total": len(self._registry),
                "healthy": healthy,
                "unhealthy": unhealthy,
                "disabled": disabled,
                "plugins": plugins_health,
            }

    def startup_all(self) -> None:
        """Start all enabled plugins and transition to RUNNING state."""
        with self._lock:
            for plugin_id, state in self._registry.items():
                if state.enabled and state._state != PluginState.RUNNING:
                    try:
                        # Step 3: Start
                        state.plugin.on_startup()
                        state._state = PluginState.RUNNING
                        logger.debug(f"Plugin started: {plugin_id}")
                    except Exception as e:
                        state.record_error(str(e))
                        logger.error(f"Plugin startup error {plugin_id}: {e}")

    def shutdown_all(self) -> None:
        """Stop all plugins and transition out of RUNNING state."""
        with self._lock:
            for plugin_id, state in self._registry.items():
                if state._state == PluginState.RUNNING:
                    try:
                        # Step 5: Stop
                        state.plugin.on_shutdown()
                        state._state = PluginState.STOPPED
                        logger.debug(f"Plugin stopped: {plugin_id}")
                    except Exception as e:
                        logger.error(f"Plugin shutdown error {plugin_id}: {e}")
                        state.record_error(str(e))

    def __len__(self) -> int:
        """Get number of registered plugins."""
        with self._lock:
            return len(self._registry)

    def __contains__(self, plugin_id: str) -> bool:
        """Check if plugin is registered."""
        with self._lock:
            return plugin_id in self._registry


# Global plugin manager instance
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager instance."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager
