"""
TACTICAL CORE — Base Event Source Adapter
WO-013-001

Provides lifecycle management and error isolation for source adapters.
"""

import threading
from typing import Any

from ..interfaces.i_event_source_adapter import IEventSourceAdapter


class BaseEventSourceAdapter(IEventSourceAdapter):
    """Base class for event source adapters with lifecycle management.

    Handles:
    - Thread-safe running state
    - Idempotent start/stop
    - Error isolation in health checks
    - Logging adapter state transitions

    Subclasses only need to implement:
    - read_events()
    - source_name()
    """

    def __init__(self) -> None:
        self._running: bool = False
        self._lock = threading.Lock()

    # --- Lifecycle ---

    def start(self) -> None:
        """Start the adapter. Idempotent and thread-safe."""
        with self._lock:
            if self._running:
                return
            self._running = True

    def stop(self) -> None:
        """Stop the adapter. Idempotent and thread-safe."""
        with self._lock:
            if not self._running:
                return
            self._running = False

    # --- Health ---

    def health(self) -> bool:
        """Check adapter health.

        Returns True if running, False otherwise.
        Error isolation: never raises.
        """
        try:
            return self._running
        except Exception:
            return False

    # --- Abstract ---

    def read_events(self) -> list[dict[str, Any]]:
        """Read events. Must be implemented by subclass."""
        raise NotImplementedError

    def source_name(self) -> str:
        """Source name. Must be implemented by subclass."""
        raise NotImplementedError

    # --- State ---

    @property
    def is_running(self) -> bool:
        """Check if adapter is currently running."""
        with self._lock:
            return self._running
