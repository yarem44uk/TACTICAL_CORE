"""
Plugin Registry.

Tracks loaded plugins and provides lookup by ID.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.plugins.sdk.base import BasePlugin
from app.plugins.discovery.plugin_discovery import DiscoveredPlugin
from app.plugins.loader.plugin_loader import LoadedPlugin

logger = logging.getLogger(__name__)


@dataclass
class RegisteredPlugin:
    """Information about a registered plugin."""

    plugin: BasePlugin
    discovered: DiscoveredPlugin
    loaded: LoadedPlugin
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    state: str = "enabled"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def plugin_id(self) -> str:
        """Get the plugin ID."""
        return self.plugin.plugin_id

    @property
    def plugin_name(self) -> str:
        """Get the plugin name."""
        return self.plugin.plugin_name

    @property
    def version(self) -> str:
        """Get the plugin version."""
        return self.plugin.version

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "plugin_id": self.plugin_id,
            "plugin_name": self.plugin_name,
            "version": self.version,
            "state": self.state,
            "registered_at": self.registered_at.isoformat(),
            "metadata": self.metadata,
        }


class PluginRegistry:
    """
    Registry for loaded plugins.

    Provides thread-safe access to registered plugins by ID.

    Usage:
        >>> registry = PluginRegistry()
        >>> registry.register(registered_plugin)
        >>> plugin = registry.get("plugin-id")
        >>> all_plugins = registry.list_plugins()
    """

    def __init__(self) -> None:
        """Initialize the plugin registry."""
        self._lock = threading.RLock()
        self._registry: Dict[str, RegisteredPlugin] = {}

    @property
    def plugin_count(self) -> int:
        """Get the number of registered plugins."""
        with self._lock:
            return len(self._registry)

    def register(self, plugin: BasePlugin, discovered: DiscoveredPlugin, loaded: LoadedPlugin) -> RegisteredPlugin:
        """
        Register a plugin.

        Args:
            plugin: Plugin instance.
            discovered: DiscoveredPlugin information.
            loaded: LoadedPlugin information.

        Returns:
            The registered plugin entry.

        Raises:
            ValueError: If plugin is already registered.
        """
        with self._lock:
            if plugin.plugin_id in self._registry:
                raise ValueError(f"Plugin {plugin.plugin_id} is already registered")

            registered = RegisteredPlugin(
                plugin=plugin,
                discovered=discovered,
                loaded=loaded,
            )

            self._registry[plugin.plugin_id] = registered
            logger.info(f"Plugin registered: {plugin.plugin_id}")
            return registered

    def unregister(self, plugin_id: str) -> bool:
        """
        Unregister a plugin.

        Args:
            plugin_id: Plugin identifier to unregister.

        Returns:
            True if the plugin was unregistered.
        """
        with self._lock:
            if plugin_id not in self._registry:
                logger.warning(f"Plugin not found for unregister: {plugin_id}")
                return False

            del self._registry[plugin_id]
            logger.info(f"Plugin unregistered: {plugin_id}")
            return True

    def get(self, plugin_id: str) -> Optional[RegisteredPlugin]:
        """
        Get a registered plugin.

        Args:
            plugin_id: Plugin identifier.

        Returns:
            RegisteredPlugin or None if not found.
        """
        with self._lock:
            return self._registry.get(plugin_id)

    def get_plugin(self, plugin_id: str) -> Optional[BasePlugin]:
        """
        Get a plugin instance.

        Args:
            plugin_id: Plugin identifier.

        Returns:
            Plugin instance or None if not found.
        """
        with self._lock:
            registered = self._registry.get(plugin_id)
            return registered.plugin if registered else None

    def list_plugins(self) -> List[BasePlugin]:
        """
        List all registered plugins.

        Returns:
            List of all plugin instances.
        """
        with self._lock:
            return [entry.plugin for entry in self._registry.values()]

    def list_registered(self) -> List[RegisteredPlugin]:
        """
        List all registered plugin entries.

        Returns:
            List of all RegisteredPlugin entries.
        """
        with self._lock:
            return list(self._registry.values())

    def is_registered(self, plugin_id: str) -> bool:
        """
        Check if a plugin is registered.

        Args:
            plugin_id: Plugin identifier.

        Returns:
            True if the plugin is registered.
        """
        with self._lock:
            return plugin_id in self._registry

    def get_all_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all registered plugins.

        Returns:
            Dictionary mapping plugin_id to plugin info.
        """
        with self._lock:
            return {
                plugin_id: entry.to_dict()
                for plugin_id, entry in self._registry.items()
            }
