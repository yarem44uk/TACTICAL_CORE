"""
Plugin Contracts.

Interfaces for plugin system.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.event.event import Event


class IPlugin(ABC):
    """
    Interface for all Tactical Core plugins.

    Plugins must implement this interface to be registered
    with the plugin system.
    """

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Unique plugin identifier."""
        pass

    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """Human-readable plugin name."""
        pass

    @property
    def version(self) -> str:
        """Plugin version. Default: 1.0.0"""
        return "1.0.0"

    @property
    def description(self) -> str:
        """Plugin description."""
        return ""

    @property
    def dependencies(self) -> List[str]:
        """List of plugin IDs this plugin depends on."""
        return []

    @abstractmethod
    def register(self) -> None:
        """Called when plugin is registered."""
        pass

    @abstractmethod
    def unregister(self) -> None:
        """Called when plugin is unregistered."""
        pass

    def on_startup(self) -> None:
        """Called when application starts. Optional."""
        pass

    def on_shutdown(self) -> None:
        """Called when application shuts down. Optional."""
        pass

    def on_event(self, event: Event) -> None:
        """
        Called for each canonical Event delivered to this plugin.

        The plugin receives the canonical ``app.event.Event`` object.
        Raw source dictionaries are never delivered here.

        Default implementation is a no-op for backward compatibility;
        plugins that handle events may override this method.

        Args:
            event: The canonical Event object to process.
        """
        pass


class IPluginManager(ABC):
    """
    Interface for plugin management.

    Manages plugin lifecycle, registration, and discovery.
    """

    @abstractmethod
    def register_plugin(self, plugin: IPlugin) -> None:
        """Register a plugin."""
        pass

    @abstractmethod
    def unregister_plugin(self, plugin_id: str) -> bool:
        """Unregister a plugin by ID."""
        pass

    @abstractmethod
    def get_plugin(self, plugin_id: str) -> Optional[IPlugin]:
        """Get a plugin by ID."""
        pass

    @abstractmethod
    def list_plugins(self) -> List[IPlugin]:
        """List all registered plugins."""
        pass

    @abstractmethod
    def enable_plugin(self, plugin_id: str) -> bool:
        """Enable a plugin."""
        pass

    @abstractmethod
    def disable_plugin(self, plugin_id: str) -> bool:
        """Disable a plugin."""
        pass

    @abstractmethod
    def get_plugin_health(self, plugin_id: str) -> Dict[str, Any]:
        """Get health status of a plugin."""
        pass
