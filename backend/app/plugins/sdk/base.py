"""
Base Plugin Class.

Abstract base class that all plugins must inherit from.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.event.event import Event
    from app.plugins.sdk.manifest import PluginManifest
    from app.plugins.sdk.context import PluginContext


class PluginState(Enum):
    """Plugin lifecycle states."""
    DISCOVERED = "discovered"
    VALIDATED = "validated"
    LOADED = "loaded"
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"
    DISABLED = "disabled"
    FAILED = "failed"
    UNINSTALLED = "uninstalled"


@dataclass
class PluginInfo:
    """Information about a plugin instance."""
    id: str
    name: str
    version: str
    author: str
    description: str
    state: PluginState = PluginState.DISCOVERED
    loaded_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BasePlugin(ABC):
    """
    Abstract base class for all Tactical Core plugins.

    Plugins must inherit from this class and implement the required
    lifecycle methods. The PluginManager handles all plugin lifecycle
    operations.

    Usage:
        >>> class MyPlugin(BasePlugin):
        ...     @property
        ...     def plugin_id(self) -> str:
        ...         return "my-plugin"
        ...
        ...     async def on_start(self) -> None:
        ...         # Initialize plugin
        ...         pass
    """

    def __init__(self, context: Optional["PluginContext"] = None) -> None:
        """
        Initialize the plugin.

        Args:
            context: Plugin execution context provided by PluginManager.
        """
        self._context = context
        self._state = PluginState.DISCOVERED
        self._info = self._create_info()

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Unique plugin identifier."""
        pass

    @property
    def plugin_name(self) -> str:
        """Human-readable plugin name."""
        return self.__class__.__name__

    @property
    def version(self) -> str:
        """Plugin version."""
        return "1.0.0"

    @property
    def author(self) -> str:
        """Plugin author."""
        return "Unknown"

    @property
    def description(self) -> str:
        """Plugin description."""
        return ""

    @property
    def dependencies(self) -> List[str]:
        """List of plugin IDs this plugin depends on."""
        return []

    @property
    def permissions(self) -> List[str]:
        """List of permissions this plugin requires."""
        return []

    @property
    def subscriptions(self) -> List[str]:
        """List of event types this plugin subscribes to."""
        return []

    @property
    def state(self) -> PluginState:
        """Current plugin state."""
        return self._state

    @property
    def info(self) -> PluginInfo:
        """Plugin information."""
        return self._info

    @property
    def context(self) -> Optional["PluginContext"]:
        """Plugin execution context."""
        return self._context

    @property
    def is_running(self) -> bool:
        """Check if plugin is currently running."""
        return self._state == PluginState.RUNNING

    def _create_info(self) -> PluginInfo:
        """Create plugin info object."""
        return PluginInfo(
            id=self.plugin_id,
            name=self.plugin_name,
            version=self.version,
            author=self.author,
            description=self.description,
        )

    def set_context(self, context: "PluginContext") -> None:
        """Set the plugin context."""
        self._context = context

    def set_state(self, state: PluginState) -> None:
        """Set the plugin state."""
        self._state = state
        self._info.state = state

    # Lifecycle Methods

    async def on_load(self) -> None:
        """
        Called when plugin is first loaded.
        Override to perform one-time initialization.
        """
        pass

    async def on_initialize(self) -> None:
        """
        Called when plugin is initialized before starting.
        Override to perform pre-start setup.
        """
        pass

    async def on_start(self) -> None:
        """
        Called when plugin starts.
        Override to perform startup operations.
        """
        pass

    async def on_stop(self) -> None:
        """
        Called when plugin stops.
        Override to perform cleanup operations.
        """
        pass

    async def on_unload(self) -> None:
        """
        Called when plugin is unloaded.
        Override to perform final cleanup.
        """
        pass

    async def on_reload(self) -> None:
        """
        Called when plugin is hot-reloaded.
        Override to handle state preservation.
        """
        pass

    async def on_health_check(self) -> bool:
        """
        Called to check plugin health.
        Override to implement custom health checks.

        Returns:
            True if healthy, False otherwise.
        """
        return self._state in (PluginState.INITIALIZED, PluginState.RUNNING)

    async def on_configuration_changed(self, config: Dict[str, Any]) -> None:
        """
        Called when plugin configuration changes.
        Override to handle configuration updates.

        Args:
            config: New configuration dictionary.
        """
        pass

    def on_event(self, event: "Event") -> None:
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

    def get_state_dict(self) -> Dict[str, Any]:
        """
        Get plugin state for hot reload.
        Override to preserve state across reloads.

        Returns:
            Dictionary containing plugin state.
        """
        return {"state": self._state.value}

    def restore_state_dict(self, state: Dict[str, Any]) -> None:
        """
        Restore plugin state from hot reload.
        Override to restore state.

        Args:
            state: Previously saved state dictionary.
        """
        if "state" in state:
            self._state = PluginState(state["state"])

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.plugin_id}, state={self._state.value})>"
