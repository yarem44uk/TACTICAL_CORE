"""
Plugin Discovery.

Automatically discovers plugins from configured directories.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.plugins.exceptions import PluginManifestError
from app.plugins.sdk.manifest import PluginManifest

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredPlugin:
    """Information about a discovered plugin."""

    plugin_id: str
    plugin_name: str
    version: str
    author: str
    description: str
    directory: Path
    entrypoint: str = "plugin:Plugin"
    manifest_path: Optional[Path] = None
    has_plugin_py: bool = False
    has_manifest_json: bool = False
    subscriptions: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    configuration: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_manifest(cls, manifest: PluginManifest, directory: Path, manifest_path: Optional[Path] = None) -> "DiscoveredPlugin":
        """Create DiscoveredPlugin from PluginManifest."""
        return cls(
            plugin_id=manifest.metadata.id,
            plugin_name=manifest.metadata.name,
            version=manifest.metadata.version,
            author=manifest.metadata.author,
            description=manifest.metadata.description,
            directory=directory,
            entrypoint=manifest.entrypoint,
            manifest_path=manifest_path,
            has_manifest_json=True,
            subscriptions=manifest.subscriptions,
            permissions=manifest.permissions,
            configuration=manifest.configuration,
            metadata=manifest.to_dict(),
        )


class PluginDiscovery:
    """
    Discovers plugins from configured directories.

    Supports two manifest formats:
    - manifest.json (JSON format)
    - plugin.py (Python module with MANIFEST dict)

    Usage:
        >>> discovery = PluginDiscovery(["/path/to/plugins"])
        >>> plugins = discovery.discover()
        >>> for plugin in plugins:
        ...     print(f"Found: {plugin.plugin_id}")
    """

    # Supported manifest filenames
    MANIFEST_JSON = "manifest.json"
    PLUGIN_PY = "plugin.py"

    def __init__(self, plugin_directories: Optional[List[str]] = None) -> None:
        """
        Initialize plugin discovery.

        Args:
            plugin_directories: List of directories to scan for plugins.
        """
        self._plugin_directories: List[Path] = [
            Path(d) for d in (plugin_directories or [])
        ]
        self._discovered: List[DiscoveredPlugin] = []

    @property
    def plugin_directories(self) -> List[Path]:
        """List of directories to scan for plugins."""
        return list(self._plugin_directories)

    def add_directory(self, directory: str) -> None:
        """Add a directory to scan."""
        self._plugin_directories.append(Path(directory))

    def remove_directory(self, directory: str) -> bool:
        """Remove a directory from scanning."""
        path = Path(directory)
        if path in self._plugin_directories:
            self._plugin_directories.remove(path)
            return True
        return False

    def discover(self) -> List[DiscoveredPlugin]:
        """
        Discover all plugins in configured directories.

        Returns:
            List of discovered plugins.
        """
        self._discovered = []

        for directory in self._plugin_directories:
            if not directory.exists() or not directory.is_dir():
                logger.warning(f"Plugin directory does not exist: {directory}")
                continue

            self._scan_directory(directory)

        logger.info(f"Discovered {len(self._discovered)} plugins")
        return self._discovered

    def _scan_directory(self, directory: Path) -> None:
        """Scan a directory for plugins."""
        try:
            for entry in directory.iterdir():
                if not entry.is_dir():
                    continue

                # Skip hidden directories and __pycache__
                if entry.name.startswith(".") or entry.name == "__pycache__":
                    continue

                # Check if this looks like a plugin directory
                if self._is_plugin_directory(entry):
                    try:
                        discovered = self._load_plugin(entry)
                        if discovered:
                            discovered = self._get_discovered(discovered)
                            self._discovered.append(discovered)
                    except Exception as e:
                        logger.error(f"Error loading plugin from {entry}: {e}")

        except OSError as e:
            logger.error(f"Error scanning directory {directory}: {e}")

    def _is_plugin_directory(self, directory: Path) -> bool:
        """Check if a directory contains a plugin."""
        # Check for manifest.json
        if (directory / self.MANIFEST_JSON).exists():
            return True

        # Check for plugin.py
        if (directory / self.PLUGIN_PY).exists():
            return True

        # Check for __init__.py (package-style plugin)
        if (directory / "__init__.py").exists():
            init_file = directory / "__init__.py"
            try:
                content = init_file.read_text(encoding="utf-8")
                # If __init__.py contains MANIFEST or imports BasePlugin, it's a plugin
                if "MANIFEST" in content or "BasePlugin" in content:
                    return True
            except OSError:
                pass

        return False

    def _load_plugin(self, directory: Path) -> Optional[DiscoveredPlugin]:
        """Load plugin information from a directory."""
        # Check which manifest formats exist
        has_json = (directory / self.MANIFEST_JSON).exists()
        has_py = (directory / self.PLUGIN_PY).exists()

        # Try manifest.json first
        if has_json:
            try:
                manifest = self._load_manifest_json(directory / self.MANIFEST_JSON)
                return DiscoveredPlugin.from_manifest(
                    manifest, directory, directory / self.MANIFEST_JSON
                )
            except PluginManifestError as e:
                logger.error(f"Invalid manifest.json in {directory}: {e}")

        # Try plugin.py
        if has_py:
            try:
                return self._load_plugin_py(directory / self.PLUGIN_PY, directory)
            except Exception as e:
                logger.error(f"Error loading plugin.py from {directory}: {e}")

        return None

    def _get_discovered(self, discovered: DiscoveredPlugin) -> DiscoveredPlugin:
        """Update discovered plugin with all available manifest info."""
        directory = discovered.directory
        if directory:
            if (directory / self.PLUGIN_PY).exists():
                discovered.has_plugin_py = True
            if (directory / self.MANIFEST_JSON).exists():
                discovered.has_manifest_json = True
        return discovered

    def _load_manifest_json(self, path: Path) -> PluginManifest:
        """Load PluginManifest from a JSON file."""
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            manifest = PluginManifest.from_dict(data)

            if not manifest.metadata.id:
                raise PluginManifestError("Manifest missing required field: id", details={"path": str(path)})

            if not manifest.metadata.name:
                raise PluginManifestError("Manifest missing required field: name", details={"path": str(path)})

            return manifest

        except json.JSONDecodeError as e:
            raise PluginManifestError(f"Invalid JSON in manifest: {e}", details={"path": str(path)})

    def _load_plugin_py(self, path: Path, directory: Path) -> DiscoveredPlugin:
        """Load plugin information from a plugin.py file."""
        content = path.read_text(encoding="utf-8")

        # Execute in isolated namespace to get MANIFEST dict
        namespace: Dict[str, Any] = {}
        try:
            exec(compile(content, str(path), "exec"), namespace)
        except SyntaxError as e:
            raise PluginManifestError(f"Syntax error in plugin.py: {e}", details={"path": str(path)})

        if "MANIFEST" not in namespace:
            raise PluginManifestError("plugin.py must define a MANIFEST dict", details={"path": str(path)})

        manifest_data = namespace["MANIFEST"]
        if not isinstance(manifest_data, dict):
            raise PluginManifestError("MANIFEST must be a dictionary", details={"path": str(path)})

        # Validate required fields
        if "id" not in manifest_data:
            raise PluginManifestError("MANIFEST missing required field: id", details={"path": str(path)})

        if "name" not in manifest_data:
            raise PluginManifestError("MANIFEST missing required field: name", details={"path": str(path)})

        # Create manifest from data
        manifest = PluginManifest.from_dict(manifest_data)
        return DiscoveredPlugin.from_manifest(manifest, directory, path)

    def get_discovered(self) -> List[DiscoveredPlugin]:
        """Get list of discovered plugins from last discovery run."""
        return list(self._discovered)

    def get_plugin_by_id(self, plugin_id: str) -> Optional[DiscoveredPlugin]:
        """Get a discovered plugin by ID."""
        for plugin in self._discovered:
            if plugin.plugin_id == plugin_id:
                return plugin
        return None
