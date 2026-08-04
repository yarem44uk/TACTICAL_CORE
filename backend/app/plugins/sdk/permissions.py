"""
Plugin Permissions.

Capability-based authorization for plugin execution.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class Permission(Enum):
    """Standard permission identifiers."""

    EVENTS_PUBLISH = "events:publish"
    EVENTS_SUBSCRIBE = "events:subscribe"
    DATABASE_READ = "database:read"
    DATABASE_WRITE = "database:write"
    FILESYSTEM_READ = "filesystem:read"
    FILESYSTEM_WRITE = "filesystem:write"
    NETWORK_HTTP = "network:http"
    NETWORK_WEBSOCKET = "network:websocket"
    MICROPHONE_READ = "microphone:read"
    CAMERA_READ = "camera:read"
    MESSAGES_SEND = "messages:send"
    MESSAGES_RECEIVE = "messages:receive"
    CODE_EXECUTE = "code:execute"
    LOGS_VIEW = "logs:view"
    CONFIG_MODIFY = "config:modify"
    PLUGINS_MANAGE = "plugins:manage"
    ADMIN = "*"


@dataclass
class PermissionDecision:
    """Result of a permission check."""

    capability: str
    granted: bool
    reason: str = ""


class PluginPermissions:
    """
    Capability-based permission manager for plugins.

    Follows deny-by-default: plugins start with no capabilities
    and must have them explicitly granted.
    """

    def __init__(self, plugin_id: str, capabilities: Optional[List[str]] = None) -> None:
        """
        Initialize permissions manager.

        Args:
            plugin_id: Unique plugin identifier.
            capabilities: Initial list of capability strings (deny-by-default if None).
        """
        self._plugin_id = plugin_id
        self._granted: Set[str] = set(capabilities) if capabilities else set()

    @property
    def plugin_id(self) -> str:
        """Plugin identifier."""
        return self._plugin_id

    @property
    def granted_capabilities(self) -> List[str]:
        """List of currently granted capabilities."""
        return sorted(self._granted)

    def grant(self, capability: str) -> bool:
        """
        Grant a capability to this plugin.

        Args:
            capability: Permission string or Permission enum value.

        Returns:
            True if the capability was newly granted, False if already present.
        """
        value = capability.value if isinstance(capability, Permission) else capability
        if value in self._granted:
            return False
        self._granted.add(value)
        return True

    def revoke(self, capability: str) -> bool:
        """
        Revoke a capability from this plugin.

        Args:
            capability: Permission string or Permission enum value.

        Returns:
            True if the capability was removed, False if it was not present.
        """
        value = capability.value if isinstance(capability, Permission) else capability
        if value not in self._granted:
            return False
        self._granted.discard(value)
        return True

    def has(self, capability: str) -> bool:
        """
        Check if the plugin has a specific capability.

        Args:
            capability: Permission string or Permission enum value.

        Returns:
            True if the capability is granted or admin wildcard is present.
        """
        value = capability.value if isinstance(capability, Permission) else capability
        return Permission.ADMIN.value in self._granted or value in self._granted

    def check(self, capability: str, reason: str = "") -> PermissionDecision:
        """
        Check a capability and return a detailed decision.

        Args:
            capability: Permission string or Permission enum value.
            reason: Optional context for the check.

        Returns:
            PermissionDecision with result and explanation.
        """
        value = capability.value if isinstance(capability, Permission) else capability
        granted = self.has(value)
        msg = "Granted" if granted else ("Wildcard admin" if Permission.ADMIN.value in self._granted else "Denied by default")
        if reason:
            msg += f" — {reason}"
        return PermissionDecision(capability=value, granted=granted, reason=msg)

    def get_permissions(self) -> Dict[str, bool]:
        """
        Get all standard permissions and their grant status.

        Returns:
            Dictionary mapping permission names to grant status.
        """
        result = {}
        for perm in Permission:
            result[perm.value] = self.has(perm.value)
        return result

    def clear(self) -> None:
        """Revoke all granted capabilities."""
        self._granted.clear()

    def is_admin(self) -> bool:
        """Check if the plugin has wildcard admin access."""
        return Permission.ADMIN.value in self._granted

    def to_dict(self) -> Dict[str, Any]:
        """Convert permissions state to dictionary."""
        return {
            "plugin_id": self._plugin_id,
            "granted": sorted(self._granted),
            "is_admin": self.is_admin(),
        }
