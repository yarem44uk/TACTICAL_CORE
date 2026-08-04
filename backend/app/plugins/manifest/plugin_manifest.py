"""
Plugin Manifest.

Handles plugin manifest.json parsing and validation.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.plugins.exceptions import PluginManifestError
from app.plugins.sdk.manifest import PluginManifest, PluginMetadata

logger = logging.getLogger(__name__)


@dataclass
class PluginManifestInfo:
    """Parsed and validated plugin manifest information."""

    plugin_id: str
    plugin_name: str
    version: str
    author: str
    description: str
    entrypoint: str
    subscriptions: List[str]
    permissions: List[str]
    configuration: Dict[str, Any]
    manifest_path: Optional[Path]
    raw_manifest: Dict[str, Any]

    @classmethod
    def from_manifest(cls, manifest: PluginManifest, path: Optional[Path] = None) -> "PluginManifestInfo":
        """Create from PluginManifest."""
        return cls(
            plugin_id=manifest.metadata.id,
            plugin_name=manifest.metadata.name,
            version=manifest.metadata.version,
            author=manifest.metadata.author,
            description=manifest.metadata.description,
            entrypoint=manifest.entrypoint,
            subscriptions=manifest.subscriptions,
            permissions=manifest.permissions,
            configuration=manifest.configuration,
            manifest_path=path,
            raw_manifest=manifest.to_dict(),
        )


class ManifestParser:
    """
    Parses and validates plugin manifests.

    Supports two formats:
    - manifest.json (JSON)
    - plugin.py (Python with MANIFEST dict)
    """

    REQUIRED_FIELDS = ["id", "name", "version"]

    def parse_json(self, path: Path) -> PluginManifestInfo:
        """
        Parse manifest.json file.

        Args:
            path: Path to manifest.json file.

        Returns:
            Parsed PluginManifestInfo.

        Raises:
            PluginManifestError: If manifest is invalid.
        """
        import json

        if not path.exists():
            raise PluginManifestError(f"Manifest not found: {path}")

        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise PluginManifestError(f"Invalid JSON in manifest: {e}")

        manifest = self._create_manifest(data, path)
        return PluginManifestInfo.from_manifest(manifest, path)

    def parse_python(self, path: Path) -> PluginManifestInfo:
        """
        Parse plugin.py file with MANIFEST dict.

        Args:
            path: Path to plugin.py file.

        Returns:
            Parsed PluginManifestInfo.

        Raises:
            PluginManifestError: If MANIFEST dict not found or invalid.
        """
        if not path.exists():
            raise PluginManifestError(f"plugin.py not found: {path}")

        content = path.read_text(encoding="utf-8")
        namespace: Dict[str, Any] = {}

        try:
            exec(compile(content, str(path), "exec"), namespace)
        except SyntaxError as e:
            raise PluginManifestError(f"Syntax error in plugin.py: {e}")

        if "MANIFEST" not in namespace:
            raise PluginManifestError(f"plugin.py must define MANIFEST dict: {path}")

        manifest_data = namespace["MANIFEST"]
        if not isinstance(manifest_data, dict):
            raise PluginManifestError(f"MANIFEST must be a dictionary: {path}")

        manifest = self._create_manifest(manifest_data, path)
        return PluginManifestInfo.from_manifest(manifest, path)

    def _create_manifest(self, data: Dict[str, Any], path: Optional[Path] = None) -> PluginManifest:
        """Create and validate PluginManifest from data."""
        manifest = PluginManifest.from_dict(data)

        # Validate required fields
        for field_name in self.REQUIRED_FIELDS:
            if field_name == "version":
                if not manifest.metadata.version:
                    raise PluginManifestError(
                        f"Manifest missing required field: {field_name}",
                        details={"path": str(path) if path else None}
                    )
            elif field_name == "id":
                if not manifest.metadata.id:
                    raise PluginManifestError(
                        f"Manifest missing required field: {field_name}",
                        details={"path": str(path) if path else None}
                    )
            elif field_name == "name":
                if not manifest.metadata.name:
                    raise PluginManifestError(
                        f"Manifest missing required field: {field_name}",
                        details={"path": str(path) if path else None}
                    )

        return manifest
