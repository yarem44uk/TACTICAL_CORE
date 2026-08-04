"""
Plugin SDK Module.

Provides base classes and interfaces for plugin development.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.plugins.sdk.base import BasePlugin, PluginState
from app.plugins.sdk.context import PluginContext
from app.plugins.sdk.manifest import PluginManifest, PluginMetadata
from app.plugins.sdk.capabilities import PluginCapabilities
from app.plugins.sdk.health import PluginHealth, PluginMetrics, HealthStatus
from app.plugins.sdk.permissions import PluginPermissions, Permission
from app.plugins.sdk.lifecycle import PluginLifecycle, LifecycleState
from app.plugins.sdk.storage import PluginStorage
from app.plugins.sdk.logger import PluginLogger

__all__ = [
    "BasePlugin",
    "PluginState",
    "PluginContext",
    "PluginManifest",
    "PluginMetadata",
    "PluginCapabilities",
    "PluginHealth",
    "PluginMetrics",
    "HealthStatus",
    "PluginPermissions",
    "Permission",
    "PluginLifecycle",
    "LifecycleState",
    "PluginStorage",
    "PluginLogger",
]
