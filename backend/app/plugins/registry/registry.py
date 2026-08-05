"""
Plugin Registry.

Passive data structure. Contains ZERO business logic.

Responsibilities ONLY:
    add(), remove(), find(), update_status(), list(), exists()

Must NOT:
    import plugins, instantiate plugins, load plugins,
    validate plugins, reload plugins, call lifecycle.

Plugin states (per WO-010-005-R1):
    DISCOVERED, VALIDATED, LOADED, RUNNING, STOPPED, FAILED, UNLOADED

Author: Tactical Core Engineering Team
Version: 1.0
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Approved state machine states
DISCOVERED = "DISCOVERED"
VALIDATED = "VALIDATED"
LOADED = "LOADED"
RUNNING = "RUNNING"
STOPPED = "STOPPED"
FAILED = "FAILED"
UNLOADED = "UNLOADED"

ALL_STATES = (DISCOVERED, VALIDATED, LOADED, RUNNING, STOPPED, FAILED, UNLOADED)


@dataclass
class RegistryEntry:
    """Immutable-by-convention registry record."""

    plugin_id: str
    plugin_name: str
    version: str
    instance: Any  # the loaded plugin instance
    status: str = DISCOVERED
    loaded_at: Optional[datetime] = None
    last_error: Optional[str] = None


class PluginRegistry:
    """
    Thread-safe passive datastore for plugin instances.

    No business logic — only CRUD operations.
    """

    def __init__(self) -> None:
        self._store: Dict[str, RegistryEntry] = {}
        self._lock = threading.RLock()

    # ---- public API -------------------------------------------------------

    def add(self, entry: RegistryEntry) -> None:
        """Add or replace a registry entry."""
        with self._lock:
            self._store[entry.plugin_id] = entry

    def remove(self, plugin_id: str) -> Optional[RegistryEntry]:
        """Remove an entry by plugin_id. Returns the removed entry or None."""
        with self._lock:
            return self._store.pop(plugin_id, None)

    def find(self, plugin_id: str) -> Optional[RegistryEntry]:
        """Return entry by plugin_id, or None."""
        with self._lock:
            return self._store.get(plugin_id)

    def exists(self, plugin_id: str) -> bool:
        """Check if plugin_id is registered."""
        with self._lock:
            return plugin_id in self._store

    def list(self) -> List[RegistryEntry]:
        """Return all entries (copy of values)."""
        with self._lock:
            return list(self._store.values())

    def update_status(self, plugin_id: str, status: str) -> bool:
        """
        Update the status field of an entry.

        Returns True if the entry existed and was updated, False otherwise.
        """
        with self._lock:
            entry = self._store.get(plugin_id)
            if entry is None:
                return False
            entry.status = status
            return True

    def update_error(self, plugin_id: str, error: str) -> bool:
        """Record an error for a plugin entry."""
        with self._lock:
            entry = self._store.get(plugin_id)
            if entry is None:
                return False
            entry.last_error = error
            entry.status = FAILED
            return True

    def get_instance(self, plugin_id: str) -> Optional[Any]:
        """Return the plugin instance or None."""
        with self._lock:
            entry = self._store.get(plugin_id)
            return entry.instance if entry else None

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def __contains__(self, plugin_id: str) -> bool:
        return self.exists(plugin_id)
