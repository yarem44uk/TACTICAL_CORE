"""
Plugin Manifest Parser.

Deserializes manifest.json into PluginMetadata.
Performs ONLY deserialization — no validation, no loading, no filesystem scan.

Output: PluginMetadata only.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# Required fields per WO-010-005-R1 Manifest Standard
REQUIRED_FIELDS = ("plugin_id", "name", "version", "sdk_version", "entrypoint", "class")


@dataclass(frozen=True)
class PluginMetadata:
    """Canonical plugin metadata from manifest."""

    plugin_id: str
    name: str
    version: str
    sdk_version: str
    author: str = "Unknown"
    entrypoint: str = "plugin.py"
    class_name: str = ""
    description: str = ""
    permissions: List[str] = field(default_factory=list)
    subscriptions: List[str] = field(default_factory=list)
    configuration: Dict[str, Any] = field(default_factory=dict)
    resources: Dict[str, str] = field(default_factory=dict)
    health_check_interval: int = 60


def parse_manifest_json(path: Path) -> PluginMetadata:
    """
    Deserialize a manifest.json file into PluginMetadata.

    Args:
        path: Absolute or relative path to manifest.json.

    Returns:
        PluginMetadata instance with all fields populated from JSON.
    """
    text = path.read_text(encoding="utf-8")
    data: Dict[str, Any] = json.loads(text)
    return _dict_to_metadata(data)


def parse_manifest_dict(data: Dict[str, Any]) -> PluginMetadata:
    """
    Deserialize a dictionary into PluginMetadata.

    Args:
        data: Dictionary with manifest key-value pairs.

    Returns:
        PluginMetadata instance.
    """
    return _dict_to_metadata(data)


def _dict_to_metadata(data: Dict[str, Any]) -> PluginMetadata:
    """Internal conversion from raw dict to PluginMetadata."""
    return PluginMetadata(
        plugin_id=data.get("plugin_id", ""),
        name=data.get("name", ""),
        version=data.get("version", ""),
        sdk_version=data.get("sdk_version", ""),
        author=data.get("author", "Unknown"),
        entrypoint=data.get("entrypoint", "plugin.py"),
        class_name=data.get("class_name", data.get("class", "")),
        description=data.get("description", ""),
        permissions=data.get("permissions", []),
        subscriptions=data.get("subscriptions", []),
        configuration=data.get("configuration", {}),
        resources=data.get("resources", {}),
        health_check_interval=data.get("health_check_interval", 60),
    )
