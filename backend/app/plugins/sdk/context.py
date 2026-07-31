"""
Plugin Context.

Provides runtime context for plugin execution.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID


@dataclass
class PluginContext:
    """
    Runtime context for plugin execution.

    Provides plugins with access to core services while maintaining
    isolation from Core implementation details.
    """

    plugin_id: str
    plugin_version: str
    api_version: str

    # Event Engine access
    event_publisher: Any = None
    event_subscriber: Any = None

    # Configuration
    config: Dict[str, Any] = field(default_factory=dict)

    # Storage
    storage_path: Optional[str] = None

    # Permissions
    permissions: List[str] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: Optional[UUID] = None
    correlation_id: Optional[str] = None

    # Sandbox
    sandbox_enabled: bool = False

    def has_permission(self, permission: str) -> bool:
        """Check if plugin has a specific permission."""
        return permission in self.permissions or "*" in self.permissions

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.config.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "plugin_id": self.plugin_id,
            "plugin_version": self.plugin_version,
            "api_version": self.api_version,
            "permissions": self.permissions,
            "storage_path": self.storage_path,
            "sandbox_enabled": self.sandbox_enabled,
            "created_at": self.created_at.isoformat(),
        }
