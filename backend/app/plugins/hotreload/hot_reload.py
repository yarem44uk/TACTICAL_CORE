"""
Plugin Hot Reload.

Supports reloading plugins without restarting the core.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.plugins.exceptions import PluginHotReloadError
from app.plugins.sdk.base import BasePlugin, PluginState
from app.plugins.discovery.plugin_discovery import DiscoveredPlugin, PluginDiscovery
from app.plugins.loader.plugin_loader import LoadedPlugin, PluginLoader
from app.plugins.registry.plugin_registry import PluginRegistry
from app.plugins.validator.plugin_validator import PluginValidator

logger = logging.getLogger(__name__)


@dataclass
class ReloadResult:
    """Result of a plugin reload operation."""

    plugin_id: str
    success: bool
    old_version: str = ""
    new_version: str = ""
    error: Optional[str] = None
    reloaded_at: Optional[datetime] = None
    state_preserved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "plugin_id": self.plugin_id,
            "success": self.success,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "error": self.error,
            "reloaded_at": self.reloaded_at.isoformat() if self.reloaded_at else None,
            "state_preserved": self.state_preserved,
        }


class PluginHotReload:
    """
    Manages hot reloading of plugins.

    Preserves plugin state during reload and validates
    the new version before activating it.

    Usage:
        >>> hot_reload = PluginHotReload(loader, registry, discovery, validator)
        >>> result = hot_reload.reload("plugin-id")
        >>> if result.success:
        ...     print(f"Reloaded to {result.new_version}")
    """

    def __init__(
        self,
        loader: PluginLoader,
        registry: PluginRegistry,
        discovery: PluginDiscovery,
        validator: PluginValidator,
    ) -> None:
        """
        Initialize hot reload manager.

        Args:
            loader: PluginLoader for loading plugins.
            registry: PluginRegistry for tracking plugins.
            discovery: PluginDiscovery for finding plugins.
            validator: PluginValidator for validating plugins.
        """
        self._loader = loader
        self._registry = registry
        self._discovery = discovery
        self._validator = validator

    def reload(self, plugin_id: str) -> ReloadResult:
        """
        Reload a plugin by ID.

        Steps:
        1. Get current plugin state
        2. Stop the plugin
        3. Unload the old version
        4. Re-discover and load the new version
        5. Validate the new version
        6. Restore state
        7. Start the new version

        Args:
            plugin_id: Plugin identifier to reload.

        Returns:
            ReloadResult with success status.
        """
        try:
            # Get current plugin
            registered = self._registry.get(plugin_id)
            if not registered:
                return ReloadResult(
                    plugin_id=plugin_id,
                    success=False,
                    error="Plugin not found in registry",
                )

            current_plugin = registered.plugin
            old_version = current_plugin.version

            # Save state
            state_dict = current_plugin.get_state_dict()
            was_running = current_plugin.is_running

            # Stop the plugin if running
            if was_running:
                try:
                    current_plugin.on_stop()
                    current_plugin.set_state(PluginState.STOPPED)
                except Exception as e:
                    logger.warning(f"Error stopping plugin {plugin_id}: {e}")

            # Unload old version
            self._loader.unload(plugin_id)
            self._registry.unregister(plugin_id)

            # Re-discover
            discovered = self._discovery.get_plugin_by_id(plugin_id)
            if not discovered:
                # Try full discovery
                self._discovery.discover()
                discovered = self._discovery.get_plugin_by_id(plugin_id)

            if not discovered:
                raise PluginHotReloadError(
                    f"Plugin not found during re-discovery: {plugin_id}"
                )

            # Load new version
            loaded = self._loader.load(discovered)
            if not loaded.is_valid:
                raise PluginHotReloadError(
                    f"Failed to load new version: {loaded.error}"
                )

            # Validate
            validation = self._validator.validate_full(discovered, loaded)
            if not validation.is_valid:
                raise PluginHotReloadError(
                    f"Validation failed: {', '.join(validation.errors)}"
                )

            # Restore state
            new_plugin = loaded.plugin
            new_plugin.restore_state_dict(state_dict)
            state_preserved = True

            # Register
            self._registry.register(new_plugin, discovered, loaded)

            # Start if was running
            if was_running:
                try:
                    new_plugin.on_start()
                    new_plugin.set_state(PluginState.RUNNING)
                except Exception as e:
                    logger.warning(f"Error starting plugin {plugin_id}: {e}")

            result = ReloadResult(
                plugin_id=plugin_id,
                success=True,
                old_version=old_version,
                new_version=new_plugin.version,
                reloaded_at=datetime.now(timezone.utc),
                state_preserved=state_preserved,
            )

            logger.info(
                f"Plugin reloaded: {plugin_id} ({old_version} -> {new_plugin.version})"
            )
            return result

        except Exception as e:
            logger.error(f"Failed to reload plugin {plugin_id}: {e}")
            return ReloadResult(
                plugin_id=plugin_id,
                success=False,
                error=str(e),
            )

    def can_reload(self, plugin_id: str) -> bool:
        """
        Check if a plugin can be reloaded.

        Args:
            plugin_id: Plugin identifier.

        Returns:
            True if the plugin can be reloaded.
        """
        return self._registry.is_registered(plugin_id)
