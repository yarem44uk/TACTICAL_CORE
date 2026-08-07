"""
TACTICAL CORE — Source Registry
WO-013-001

Thread-safe registry for managing multiple event source adapters.
"""

import threading
import logging
from typing import Any

from ..interfaces.i_event_source_adapter import IEventSourceAdapter

logger = logging.getLogger(__name__)


class SourceRegistry:
    """Thread-safe registry for event source adapters.

    Responsibilities:
    - Register/unregister adapters by name
    - Start/stop all adapters with failure isolation
    - List registered sources
    - Lookup by name

    One adapter failure must not stop others.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, IEventSourceAdapter] = {}
        self._lock = threading.Lock()

    def register(self, adapter: IEventSourceAdapter) -> None:
        """Register an adapter.

        Args:
            adapter: Source adapter instance.

        Raises:
            ValueError: If an adapter with the same name is already registered.
        """
        name = adapter.source_name()
        with self._lock:
            if name in self._adapters:
                raise ValueError(f"Adapter '{name}' already registered")
            self._adapters[name] = adapter
        logger.info("Registered adapter: %s", name)

    def unregister(self, name: str) -> None:
        """Unregister an adapter by name.

        Args:
            name: Source name to unregister.

        Raises:
            KeyError: If no adapter with the given name exists.
        """
        with self._lock:
            if name not in self._adapters:
                raise KeyError(f"Adapter '{name}' not found")
            adapter = self._adapters.pop(name)
        try:
            adapter.stop()
        except Exception as e:
            logger.error("Error stopping adapter '%s': %s", name, e)
        logger.info("Unregistered adapter: %s", name)

    def get(self, name: str) -> IEventSourceAdapter:
        """Get adapter by name.

        Args:
            name: Source name.

        Returns:
            The registered adapter.

        Raises:
            KeyError: If no adapter with the given name exists.
        """
        with self._lock:
            if name not in self._adapters:
                raise KeyError(f"Adapter '{name}' not found")
            return self._adapters[name]

    def list_sources(self) -> list[str]:
        """List all registered source names.

        Returns:
            Sorted list of source names.
        """
        with self._lock:
            return sorted(self._adapters.keys())

    def start_all(self) -> None:
        """Start all registered adapters.

        One adapter failure does not prevent others from starting.
        """
        names = self.list_sources()
        for name in names:
            try:
                adapter = self.get(name)
                adapter.start()
                logger.info("Started adapter: %s", name)
            except Exception as e:
                logger.error("Failed to start adapter '%s': %s", name, e)

    def stop_all(self) -> None:
        """Stop all registered adapters.

        One adapter failure does not prevent others from stopping.
        """
        names = self.list_sources()
        for name in names:
            try:
                adapter = self.get(name)
                adapter.stop()
                logger.info("Stopped adapter: %s", name)
            except Exception as e:
                logger.error("Failed to stop adapter '%s': %s", name, e)

    def count(self) -> int:
        """Return the number of registered adapters."""
        with self._lock:
            return len(self._adapters)
