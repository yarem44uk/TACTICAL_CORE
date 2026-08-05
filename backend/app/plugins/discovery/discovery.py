"""
Plugin Discovery.

Performs ONLY filesystem scanning.
Does NOT: parse manifests, import modules, validate, or instantiate.

Output: list of PluginCandidate (path + type).

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class PluginCandidate:
    """Result of filesystem discovery — filesystem-only information."""

    path: Path
    candidate_type: str  # "manifest" or "plugin_py"


def discover(
    root_paths: List[Path],
    *,
    manifest_name: str = "manifest.json",
    entrypoint_name: str = "plugin.py",
) -> List[PluginCandidate]:
    """
    Scan directories for plugin directories that contain either
    ``manifest.json`` or ``plugin.py``.

    Args:
        root_paths: Directories to scan (e.g. ``plugins/``).
        manifest_name: Filename to look for (default ``manifest.json``).
        entrypoint_name: Fallback filename (default ``plugin.py``).

    Returns:
        List of PluginCandidate — purely filesystem data.
    """
    candidates: List[PluginCandidate] = []
    seen: set[str] = set()

    for root in root_paths:
        _scan_directory(root, manifest_name, entrypoint_name, candidates, seen)

    return candidates


def _scan_directory(
    root: Path,
    manifest_name: str,
    entrypoint_name: str,
    candidates: List[PluginCandidate],
    seen: set[str],
) -> None:
    if not root.is_dir():
        return

    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue

        # Skip virtual-environments, caches, hidden dirs
        if entry.name.startswith(".") or entry.name in (
            "__pycache__", "venv", ".venv", "node_modules", ".git",
        ):
            continue

        plugin_id = entry.name
        if plugin_id in seen:
            continue

        # Prefer manifest.json over plugin.py
        manifest_path = entry / manifest_name
        if manifest_path.is_file():
            candidates.append(PluginCandidate(path=entry, candidate_type="manifest"))
            seen.add(plugin_id)
            continue

        entrypoint_path = entry / entrypoint_name
        if entrypoint_path.is_file():
            candidates.append(PluginCandidate(path=entry, candidate_type="plugin_py"))
            seen.add(plugin_id)
