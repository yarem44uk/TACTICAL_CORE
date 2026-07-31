"""
Plugin SDK Module.

Provides base classes and interfaces for plugin development.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.plugins.sdk.base import BasePlugin, PluginContext, PluginState
from app.plugins.sdk.manifest import PluginManifest, PluginMetadata
from app.plugins.sdk.capabilities import PluginCapabilities
from app.plugins.sdk.health import PluginHealth, PluginMetrics
from app.plugins.sdk.permissions import PluginPermissions, Permission
from app.plugins.sdk.lifecycle import PluginLifecycle, LifecycleState
from app.plugins.sdk.storage import PluginStorage
from app.plugins.sdk.logger import PluginLogger

__all__ = [
    "BasePlugin",
    "PluginContext",
    "PluginState",
    "PluginManifest",
    "PluginMetadata",
    "PluginCapabilities",
    "PluginHealth",
    "PluginMetrics",
    "PluginPermissions",
    "Permission",
    "PluginLifecycle",
    "LifecycleState",
    "PluginStorage",
    "PluginLogger",
]
