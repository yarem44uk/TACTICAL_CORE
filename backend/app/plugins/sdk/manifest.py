"""
Plugin Manifest.

Defines plugin metadata and configuration.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PluginMetadata:
    """Plugin metadata from manifest."""
    id: str
    name: str
    version: str
    author: str
    description: str
    minimum_core_version: str = "1.0.0"
    api_version: str = "1.0"
    license: str = "MIT"
    home_page: Optional[str] = None
    repository: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    dependencies: Dict[str, str] = field(default_factory=dict)


@dataclass
class PluginManifest:
    """Plugin manifest containing all plugin metadata."""

    metadata: PluginMetadata
    entrypoint: str = "plugin:Plugin"
    subscriptions: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    configuration: Dict[str, Any] = field(default_factory=dict)
    resources: Dict[str, str] = field(default_factory=dict)
    health_check_interval: int = 60

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        """Create manifest from dictionary."""
        metadata = PluginMetadata(
            id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", "Unknown"),
            description=data.get("description", ""),
            minimum_core_version=data.get("minimum_core_version", "1.0.0"),
            api_version=data.get("api_version", "1.0"),
            license=data.get("license", "MIT"),
            home_page=data.get("home_page"),
            repository=data.get("repository"),
            keywords=data.get("keywords", []),
            dependencies=data.get("dependencies", {}),
        )

        return cls(
            metadata=metadata,
            entrypoint=data.get("entrypoint", "plugin:Plugin"),
            subscriptions=data.get("subscriptions", []),
            permissions=data.get("permissions", []),
            configuration=data.get("configuration", {}),
            resources=data.get("resources", {}),
            health_check_interval=data.get("health_check_interval", 60),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert manifest to dictionary."""
        return {
            "id": self.metadata.id,
            "name": self.metadata.name,
            "version": self.metadata.version,
            "author": self.metadata.author,
            "description": self.metadata.description,
            "minimum_core_version": self.metadata.minimum_core_version,
            "api_version": self.metadata.api_version,
            "license": self.metadata.license,
            "home_page": self.metadata.home_page,
            "repository": self.metadata.repository,
            "keywords": self.metadata.keywords,
            "dependencies": self.metadata.dependencies,
            "entrypoint": self.entrypoint,
            "subscriptions": self.subscriptions,
            "permissions": self.permissions,
            "configuration": self.configuration,
            "resources": self.resources,
            "health_check_interval": self.health_check_interval,
        }
