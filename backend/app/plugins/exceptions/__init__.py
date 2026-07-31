"""
Plugin Exceptions.

Custom exceptions for the plugin system.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from typing import Any, Optional


class PluginException(Exception):
    """Base exception for plugin system."""

    def __init__(
        self,
        message: str,
        plugin_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.plugin_id = plugin_id
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "message": str(self),
            "plugin_id": self.plugin_id,
            "details": self.details,
        }


class PluginNotFoundError(PluginException):
    """Raised when plugin is not found."""
    pass


class PluginLoadError(PluginException):
    """Raised when plugin fails to load."""
    pass


class PluginInitError(PluginException):
    """Raised when plugin fails to initialize."""
    pass


class PluginStartError(PluginException):
    """Raised when plugin fails to start."""
    pass


class PluginStopError(PluginException):
    """Raised when plugin fails to stop."""
    pass


class PluginUnloadError(PluginException):
    """Raised when plugin fails to unload."""
    pass


class PluginValidationError(PluginException):
    """Raised when plugin validation fails."""
    pass


class PluginDependencyError(PluginException):
    """Raised when plugin dependencies are not met."""
    pass


class PluginPermissionError(PluginException):
    """Raised when plugin lacks required permissions."""
    pass


class PluginVersionError(PluginException):
    """Raised when plugin version is incompatible."""
    pass


class PluginManifestError(PluginException):
    """Raised when plugin manifest is invalid."""
    pass


class PluginSandboxError(PluginException):
    """Raised when sandbox violation occurs."""
    pass


class PluginHotReloadError(PluginException):
    """Raised when plugin hot reload fails."""
    pass


class PluginConfigurationError(PluginException):
    """Raised when plugin configuration is invalid."""
    pass
