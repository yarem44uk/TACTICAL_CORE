"""
Plugins Module.

Provides plugin system for Tactical Core.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from app.plugins.manager.plugin_manager import PluginManager, get_plugin_manager
from app.plugins.signal_reference_plugin import SignalReferencePlugin

__all__ = [
    "PluginManager",
    "get_plugin_manager",
    "SignalReferencePlugin",
]
