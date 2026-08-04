"""
Plugin Loader.

Loads plugin modules and creates plugin instances.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
import sys
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional, Type

from app.plugins.exceptions import PluginLoadError, PluginValidationError
from app.plugins.sdk.base import BasePlugin
from app.plugins.sdk.context import PluginContext
from app.plugins.discovery.plugin_discovery import DiscoveredPlugin

logger = logging.getLogger(__name__)


@dataclass
class LoadedPlugin:
    """Information about a loaded plugin."""

    plugin: BasePlugin
    discovered: DiscoveredPlugin
    module: Optional[ModuleType] = None
    loaded_at: Optional[str] = None
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Check if the plugin was loaded successfully."""
        return self.error is None


class PluginLoader:
    """
    Loads plugins from discovered plugin directories.

    Handles module import, instance creation, and validation.

    Usage:
        >>> loader = PluginLoader()
        >>> loaded = loader.load(discovered_plugin)
        >>> if loaded.is_valid:
        ...     plugin = loaded.plugin
    """

    def __init__(self) -> None:
        """Initialize the plugin loader."""
        self._loaded_modules: Dict[str, ModuleType] = {}
        self._loaded_plugins: Dict[str, LoadedPlugin] = {}

    @property
    def loaded_plugins(self) -> Dict[str, LoadedPlugin]:
        """Get all loaded plugins."""
        return dict(self._loaded_plugins)

    def load(self, discovered: DiscoveredPlugin, context: Optional[PluginContext] = None) -> LoadedPlugin:
        """
        Load a discovered plugin.

        Args:
            discovered: DiscoveredPlugin information.
            context: Optional PluginContext to inject.

        Returns:
            LoadedPlugin with the plugin instance or error.
        """
        from datetime import datetime, timezone

        try:
            module = self._import_module(discovered)
            plugin_class = self._resolve_plugin_class(module, discovered.entrypoint)
            plugin = self._create_instance(plugin_class, context)
            self._validate_plugin(plugin, discovered)

            loaded = LoadedPlugin(
                plugin=plugin,
                discovered=discovered,
                module=module,
                loaded_at=datetime.now(timezone.utc).isoformat(),
            )

            self._loaded_modules[discovered.plugin_id] = module
            self._loaded_plugins[discovered.plugin_id] = loaded

            logger.info(f"Loaded plugin: {discovered.plugin_id} ({discovered.plugin_name})")
            return loaded

        except Exception as e:
            logger.error(f"Failed to load plugin {discovered.plugin_id}: {e}")
            return LoadedPlugin(
                plugin=None,  # type: ignore
                discovered=discovered,
                error=str(e),
            )

    def unload(self, plugin_id: str) -> bool:
        """
        Unload a plugin by ID.

        Args:
            plugin_id: Plugin identifier to unload.

        Returns:
            True if the plugin was unloaded.
        """
        if plugin_id not in self._loaded_plugins:
            return False

        loaded = self._loaded_plugins.pop(plugin_id)

        # Remove module from sys.modules to allow reload
        if loaded.module and loaded.module.__name__ in sys.modules:
            del sys.modules[loaded.module.__name__]

        if plugin_id in self._loaded_modules:
            del self._loaded_modules[plugin_id]

        logger.info(f"Unloaded plugin: {plugin_id}")
        return True

    def reload(self, plugin_id: str, discovered: DiscoveredPlugin, context: Optional[PluginContext] = None) -> LoadedPlugin:
        """
        Reload a plugin.

        Args:
            plugin_id: Plugin identifier to reload.
            discovered: Updated DiscoveredPlugin information.
            context: Optional PluginContext to inject.

        Returns:
            LoadedPlugin with the new plugin instance.
        """
        self.unload(plugin_id)
        return self.load(discovered, context)

    def _import_module(self, discovered: DiscoveredPlugin) -> ModuleType:
        """Import a plugin module."""
        # Add plugin directory to path temporarily
        plugin_dir = str(discovered.directory.parent)
        if plugin_dir not in sys.path:
            sys.path.insert(0, plugin_dir)

        try:
            # Try to import from the plugin directory
            module_name = discovered.directory.name
            module = import_module(f".{module_name}", package="")
            return module
        except ImportError:
            # Try direct import
            try:
                module = import_module(module_name)
                return module
            except ImportError as e:
                raise PluginLoadError(
                    f"Cannot import plugin module: {module_name}",
                    plugin_id=discovered.plugin_id,
                    details={"error": str(e)}
                )
        finally:
            # Clean up sys.path
            if plugin_dir in sys.path:
                sys.path.remove(plugin_dir)

    def _resolve_plugin_class(self, module: ModuleType, entrypoint: str) -> Type[BasePlugin]:
        """
        Resolve the plugin class from the module using the entrypoint.

        Format: "module_path:ClassName" or just "ClassName"
        """
        if ":" in entrypoint:
            module_path, class_name = entrypoint.rsplit(":", 1)
            # Import the specific module path
            try:
                target_module = import_module(module_path)
            except ImportError:
                target_module = module

            if not hasattr(target_module, class_name):
                raise PluginValidationError(
                    f"Entrypoint class not found: {entrypoint}",
                    plugin_id=""
                )

            plugin_class = getattr(target_module, class_name)
        else:
            class_name = entrypoint
            if hasattr(module, class_name):
                plugin_class = getattr(module, class_name)
            else:
                # Try to find a class that inherits from BasePlugin
                for name in dir(module):
                    attr = getattr(module, name)
                    if isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin:
                        plugin_class = attr
                        break
                else:
                    raise PluginValidationError(
                        f"No BasePlugin subclass found in module",
                        plugin_id=""
                    )

        # Verify it's a BasePlugin subclass
        if not isinstance(plugin_class, type) or not issubclass(plugin_class, BasePlugin):
            raise PluginValidationError(
                f"Entrypoint is not a BasePlugin subclass: {entrypoint}",
                plugin_id=""
            )

        return plugin_class

    def _create_instance(self, plugin_class: Type[BasePlugin], context: Optional[PluginContext] = None) -> BasePlugin:
        """Create a plugin instance."""
        try:
            if context:
                instance = plugin_class(context=context)
            else:
                instance = plugin_class()
            return instance
        except Exception as e:
            raise PluginLoadError(
                f"Failed to create plugin instance: {e}",
                plugin_id=""
            )

    def _validate_plugin(self, plugin: BasePlugin, discovered: DiscoveredPlugin) -> None:
        """Validate the loaded plugin."""
        if not plugin.plugin_id:
            raise PluginValidationError(
                "Plugin must have a non-empty plugin_id",
                plugin_id=""
            )

        # Verify plugin_id matches manifest
        if plugin.plugin_id != discovered.plugin_id:
            raise PluginValidationError(
                f"Plugin ID mismatch: manifest={discovered.plugin_id}, actual={plugin.plugin_id}",
                plugin_id=plugin.plugin_id
            )
