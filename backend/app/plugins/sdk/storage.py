"""
Plugin Storage.

Persistent key-value storage for plugin state.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


class PluginStorage:
    """
    File-based key-value storage for plugin state persistence.

    Each plugin gets an isolated storage file. Data is loaded
    on initialization and persisted on demand. Thread-safe.
    """

    def __init__(self, plugin_id: str, storage_path: Optional[str] = None) -> None:
        """
        Initialize plugin storage.

        Args:
            plugin_id: Unique plugin identifier (used for file naming).
            storage_path: Base directory for storage files. Defaults to ~/.tactical_core/plugins.
        """
        self._plugin_id = plugin_id
        self._data: Dict[str, Any] = {}
        self._lock = threading.RLock()

        base = Path(storage_path) if storage_path else Path.home() / ".tactical_core" / "plugins"
        base.mkdir(parents=True, exist_ok=True)
        self._file = base / f"{plugin_id}.json"
        self._load()

    @property
    def plugin_id(self) -> str:
        """Plugin identifier."""
        return self._plugin_id

    @property
    def storage_path(self) -> Path:
        """Path to the storage file."""
        return self._file

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value by key.

        Args:
            key: Storage key.
            default: Default value if key does not exist.

        Returns:
            Stored value or default.
        """
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Set a key-value pair.

        Args:
            key: Storage key.
            value: Value to store.
        """
        with self._lock:
            self._data[key] = value

    def delete(self, key: str) -> bool:
        """
        Delete a key.

        Args:
            key: Storage key to remove.

        Returns:
            True if the key existed and was removed.
        """
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    def keys(self) -> List[str]:
        """
        Get all stored keys.

        Returns:
            List of all keys in storage.
        """
        with self._lock:
            return list(self._data.keys())

    def has(self, key: str) -> bool:
        """
        Check if a key exists.

        Args:
            key: Storage key to check.

        Returns:
            True if key exists.
        """
        with self._lock:
            return key in self._data

    def clear(self) -> None:
        """Remove all stored data (in-memory only)."""
        with self._lock:
            self._data.clear()

    def persist(self) -> None:
        """Write current data to disk."""
        with self._lock:
            self._save()

    def reset(self) -> None:
        """Clear in-memory data and remove the storage file."""
        with self._lock:
            self._data.clear()
            if self._file.exists():
                self._file.unlink()

    def _load(self) -> None:
        """Load data from disk."""
        if self._file.exists():
            try:
                raw = self._file.read_text(encoding="utf-8")
                self._data = json.loads(raw)
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self) -> None:
        """Save data to disk."""
        try:
            self._file.write_text(json.dumps(self._data, indent=2, default=str), encoding="utf-8")
        except OSError:
            pass  # Storage is best-effort; do not crash the plugin

    def to_dict(self) -> Dict[str, Any]:
        """Convert storage state to dictionary."""
        with self._lock:
            return {
                "plugin_id": self._plugin_id,
                "storage_path": str(self._file),
                "keys": list(self._data.keys()),
                "key_count": len(self._data),
            }
