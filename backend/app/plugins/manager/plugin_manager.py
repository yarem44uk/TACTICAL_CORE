"""
Plugin Manager Implementation.

Implements IPluginManager interface with Discovery, Loader, Registry, and Validator.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.contracts.plugin import IPlugin, IPluginManager
from app.plugins.discovery.plugin_discovery import PluginDiscovery, DiscoveredPlugin
from app.plugins.loader.plugin_loader import PluginLoader, LoadedPlugin
from app.plugins.registry.plugin_registry import PluginRegistry, RegisteredPlugin
from app.plugins.validator.plugin_validator import PluginValidator
from app.plugins.hotreload.hot_reload import PluginHotReload
from app.plugins.exceptions import PluginLoadError, PluginValidationError

logger = logging.getLogger(__name__)


class PluginManager(IPluginManager):
    """
    Plugin Manager implementation with automatic discovery.

    Manages plugin lifecycle, registration, and discovery.
    Thread-safe implementation using RLock.

    Lifecycle Order:
        initialize() -> register() -> start() -> publish() -> stop() -> unregister()

    Architecture:
        PluginManager
            ├── PluginDiscovery (finds plugins)
            ├── PluginLoader (loads plugins)
            ├── PluginRegistry (tracks plugins)
            ├── PluginValidator (validates plugins)
            └── PluginHotReload (reloads plugins)

    Attributes:
        _registry: Internal plugin registry.
        _lock: Thread safety lock.

    Usage:
        >>> manager = PluginManager(["/path/to/plugins"])
        >>> manager.auto_discover_and_register()
        >>> plugin = manager.get_plugin("my-plugin-id")
        >>> manager.enable_plugin("my-plugin-id")
    """

    def __init__(
        self,
        plugin_directories: Optional[List[str]] = None,
        discovery: Optional[PluginDiscovery] = None,
        loader: Optional[PluginLoader] = None,
        registry: Optional[PluginRegistry] = None,
        validator: Optional[PluginValidator] = None,
    ) -> None:
        """
        Initialize the Plugin Manager.

        Args:
            plugin_directories: Directories to scan for plugins.
            discovery: Optional PluginDiscovery instance.
            loader: Optional PluginLoader instance.
            registry: Optional PluginRegistry instance.
            validator: Optional PluginValidator instance.
        """
        self._lock = threading.RLock()
        self._registry = registry or PluginRegistry()
        self._discovery = discovery or PluginDiscovery(plugin_directories)
        self._loader = loader or PluginLoader()
        self._validator = validator or PluginValidator()
        self._hot_reload = PluginHotReload(
            self._loader,
            self._registry,
            self._discovery,
            self._validator,
        )
        self._event_bus = None
        self._event_engine = None

        logger.info("PluginManager initialized")

    @property
    def discovery(self) -> PluginDiscovery:
        """Get the plugin discovery instance."""
        return self._discovery

    @property
    def loader(self) -> PluginLoader:
        """Get the plugin loader instance."""
        return self._loader

    @property
    def validator(self) -> PluginValidator:
        """Get the plugin validator instance."""
        return self._validator

    @property
    def hot_reload(self) -> PluginHotReload:
        """Get the hot reload manager instance."""
        return self._hot_reload

    def set_event_bus(self, event_bus: Any) -> None:
        """Set the event bus for plugin communication."""
        with self._lock:
            self._event_bus = event_bus

    def set_event_engine(self, event_engine: Any) -> None:
        """Set the event engine for plugin communication."""
        with self._lock:
            self._event_engine = event_engine

    def auto_discover_and_register(self) -> int:
        """
        Discover plugins and register them automatically.

        Returns:
            Number of plugins registered.
        """
        with self._lock:
            # Discover plugins
            discovered_plugins = self._discovery.discover()
            registered_count = 0

            for discovered in discovered_plugins:
                try:
                    # Validate manifest
                    manifest_result = self._validator.validate_manifest(discovered)
                    if not manifest_result.is_valid:
                        logger.warning(
                            f"Plugin {discovered.plugin_id} failed validation: {manifest_result.errors}"
                        )
                        continue

                    # Load plugin
                    loaded = self._loader.load(discovered)
                    if not loaded.is_valid:
                        logger.error(f"Failed to load plugin {discovered.plugin_id}: {loaded.error}")
                        continue

                    # Validate loaded plugin
                    validation = self._validator.validate_full(discovered, loaded)
                    if not validation.is_valid:
                        logger.warning(
                            f"Plugin {discovered.plugin_id} failed validation: {validation.errors}"
                        )
                        continue

                    # Register plugin
                    self._registry.register(loaded.plugin, discovered, loaded)
                    registered_count += 1
                    logger.info(f"Auto-registered plugin: {discovered.plugin_id}")

                except Exception as e:
                    logger.error(f"Error registering plugin {discovered.plugin_id}: {e}")

            logger.info(f"Auto-discovered and registered {registered_count} plugins")
            return registered_count

    def register_plugin(self, plugin: IPlugin) -> None:
        """
        Register a plugin manually.

        Args:
            plugin: Plugin instance to register.

        Raises:
            ValueError: If plugin is already registered.
        """
        with self._lock:
            if self._registry.is_registered(plugin.plugin_id):
                raise ValueError(f"Plugin {plugin.plugin_id} is already registered")

            try:
                # Create discovered info for manual registration
                discovered = DiscoveredPlugin(
                    plugin_id=plugin.plugin_id,
                    plugin_name=plugin.plugin_name,
                    version=getattr(plugin, "version", "1.0.0"),
                    author=getattr(plugin, "author", "Unknown"),
                    description=getattr(plugin, "description", ""),
                    directory=None,
                )

                loaded = LoadedPlugin(
                    plugin=plugin,
                    discovered=discovered,
                )

                # Validate
                validation = self._validator.validate_base_plugin(loaded)
                if not validation.is_valid:
                    raise PluginValidationError(
                        f"Plugin validation failed: {', '.join(validation.errors)}",
                        plugin_id=plugin.plugin_id
                    )

                # Register
                self._registry.register(plugin, discovered, loaded)
                logger.info(f"Plugin registered: {plugin.plugin_id}")

            except Exception as e:
                logger.error(f"Failed to register plugin {plugin.plugin_id}: {e}")
                raise

    def unregister_plugin(self, plugin_id: str) -> bool:
        """
        Unregister a plugin by ID.

        Args:
            plugin_id: Plugin identifier to unregister.

        Returns:
            True if the plugin was unregistered.
        """
        with self._lock:
            if not self._registry.is_registered(plugin_id):
                logger.warning(f"Plugin not found for unregister: {plugin_id}")
                return False

            try:
                # Unload if needed
                self._loader.unload(plugin_id)

                # Unregister
                self._registry.unregister(plugin_id)
                logger.info(f"Plugin unregistered: {plugin_id}")
                return True

            except Exception as e:
                logger.error(f"Error during plugin unregister {plugin_id}: {e}")
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
            return self._registry.get_plugin(plugin_id)

    def list_plugins(self) -> List[IPlugin]:
        """
        List all registered plugins.

        Returns:
            List of all plugin instances.
        """
        with self._lock:
            return self._registry.list_plugins()

    def enable_plugin(self, plugin_id: str) -> bool:
        """
        Enable a plugin.

        Args:
            plugin_id: Plugin identifier to enable.

        Returns:
            True if the plugin was enabled.
        """
        with self._lock:
            registered = self._registry.get(plugin_id)
            if registered is None:
                logger.warning(f"Plugin not found for enable: {plugin_id}")
                return False

            # Mark as enabled
            registered.state = "enabled"
            logger.info(f"Plugin enabled: {plugin_id}")
            return True

    def disable_plugin(self, plugin_id: str) -> bool:
        """
        Disable a plugin.

        Args:
            plugin_id: Plugin identifier to disable.

        Returns:
            True if the plugin was disabled.
        """
        with self._lock:
            registered = self._registry.get(plugin_id)
            if registered is None:
                logger.warning(f"Plugin not found for disable: {plugin_id}")
                return False

            registered.state = "disabled"
            logger.info(f"Plugin disabled: {plugin_id}")
            return True

    def reload_plugin(self, plugin_id: str) -> bool:
        """
        Reload a plugin.

        Args:
            plugin_id: Plugin identifier to reload.

        Returns:
            True if the plugin was reloaded successfully.
        """
        with self._lock:
            result = self._hot_reload.reload(plugin_id)
            if result.success:
                logger.info(f"Plugin reloaded: {plugin_id} ({result.old_version} -> {result.new_version})")
            else:
                logger.error(f"Failed to reload plugin {plugin_id}: {result.error}")
            return result.success

    def get_plugin_health(self, plugin_id: str) -> Dict[str, Any]:
        """
        Get health status of a plugin.

        Args:
            plugin_id: Plugin identifier.

        Returns:
            Dictionary with health information.
        """
        with self._lock:
            registered = self._registry.get(plugin_id)

            if registered is None:
                return {
                    "status": "unknown",
                    "plugin_id": plugin_id,
                    "error": "Plugin not found",
                }

            plugin = registered.plugin
            status = "healthy"
            if registered.state == "disabled":
                status = "disabled"
            elif hasattr(plugin, "health"):
                status = plugin.health.status.value if plugin.health.status else "unknown"

            return {
                "plugin_id": plugin_id,
                "plugin_name": plugin.plugin_name,
                "status": status,
                "state": registered.state,
                "enabled": registered.state == "enabled",
                "version": plugin.version,
                "registered_at": registered.registered_at.isoformat(),
                "description": plugin.description,
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

            for registered in self._registry.list_registered():
                health = self.get_plugin_health(registered.plugin_id)
                plugins_health[registered.plugin_id] = health

                status = health["status"]
                if status == "healthy":
                    healthy += 1
                elif status == "unhealthy":
                    unhealthy += 1
                elif status == "disabled":
                    disabled += 1

            return {
                "total": self._registry.plugin_count,
                "healthy": healthy,
                "unhealthy": unhealthy,
                "disabled": disabled,
                "plugins": plugins_health,
            }

    def startup_all(self) -> None:
        """Start all enabled plugins."""
        with self._lock:
            for registered in self._registry.list_registered():
                if registered.state == "enabled":
                    try:
                        registered.plugin.on_start()
                        logger.debug(f"Plugin started: {registered.plugin_id}")
                    except Exception as e:
                        logger.error(f"Plugin startup error {registered.plugin_id}: {e}")

    def shutdown_all(self) -> None:
        """Stop all enabled plugins."""
        with self._lock:
            for registered in self._registry.list_registered():
                if registered.state == "enabled":
                    try:
                        registered.plugin.on_stop()
                        logger.debug(f"Plugin stopped: {registered.plugin_id}")
                    except Exception as e:
                        logger.error(f"Plugin shutdown error {registered.plugin_id}: {e}")

    def __len__(self) -> int:
        """Get number of registered plugins."""
        with self._lock:
            return self._registry.plugin_count

    def __contains__(self, plugin_id: str) -> bool:
        """Check if plugin is registered."""
        with self._lock:
            return self._registry.is_registered(plugin_id)


# Global plugin manager instance
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager instance."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager
