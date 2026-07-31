"""
Plugin Capabilities.

Defines plugin capabilities and features.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from typing import List, Set


@dataclass
class PluginCapabilities:
    """Plugin capabilities definition."""

    can_publish_events: bool = True
    can_subscribe_events: bool = True
    can_access_database: bool = False
    can_access_filesystem: bool = False
    can_access_network: bool = False
    can_access_microphone: bool = False
    can_access_camera: bool = False
    can_send_messages: bool = False
    can_execute_code: bool = False
    can_view_logs: bool = True
    can_modify_config: bool = False
    can_manage_plugins: bool = False

    custom_capabilities: Set[str] = field(default_factory=set)

    @classmethod
    def from_permissions(cls, permissions: List[str]) -> "PluginCapabilities":
        """Create capabilities from permission list."""
        caps = cls()

        permission_map = {
            "events:publish": "can_publish_events",
            "events:subscribe": "can_subscribe_events",
            "database:read": "can_access_database",
            "database:write": "can_access_database",
            "filesystem:read": "can_access_filesystem",
            "filesystem:write": "can_access_filesystem",
            "network:http": "can_access_network",
            "network:websocket": "can_access_network",
            "microphone:read": "can_access_microphone",
            "camera:read": "can_access_camera",
            "messages:send": "can_send_messages",
            "messages:receive": "can_send_messages",
            "code:execute": "can_execute_code",
            "logs:view": "can_view_logs",
            "config:modify": "can_modify_config",
            "plugins:manage": "can_manage_plugins",
        }

        for permission in permissions:
            if permission in permission_map:
                attr = permission_map[permission]
                setattr(caps, attr, True)
            elif permission.startswith("custom:"):
                caps.custom_capabilities.add(permission)

        return caps

    def to_permissions(self) -> List[str]:
        """Convert capabilities to permission list."""
        permissions = []

        cap_map = {
            "can_publish_events": "events:publish",
            "can_subscribe_events": "events:subscribe",
            "can_access_database": "database:read",
            "can_access_filesystem": "filesystem:read",
            "can_access_network": "network:http",
            "can_access_microphone": "microphone:read",
            "can_access_camera": "camera:read",
            "can_send_messages": "messages:send",
            "can_execute_code": "code:execute",
            "can_view_logs": "logs:view",
            "can_modify_config": "config:modify",
            "can_manage_plugins": "plugins:manage",
        }

        for attr, permission in cap_map.items():
            if getattr(self, attr, False):
                permissions.append(permission)

        permissions.extend(self.custom_capabilities)
        return permissions
