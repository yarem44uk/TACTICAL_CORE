"""
TACTICAL CORE — Event Source Adapter Interface
WO-013-001

Contract that all external data source adapters must implement.
"""

from abc import ABC, abstractmethod
from typing import Any


class IEventSourceAdapter(ABC):
    """Contract for external event source adapters.

    Each adapter is responsible for connecting to one type of external source
    (e.g. Telegram, Signal, MQTT) and reading raw events from it.
    """

    @abstractmethod
    def start(self) -> None:
        """Start the adapter and begin reading events.

        Idempotent: calling start() on an already running adapter is safe.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop the adapter and release resources.

        Idempotent: calling stop() on an already stopped adapter is safe.
        """
        ...

    @abstractmethod
    def health(self) -> bool:
        """Check adapter health.

        Returns:
            True if the adapter is connected and operational, False otherwise.
        """
        ...

    @abstractmethod
    def read_events(self) -> list[dict[str, Any]]:
        """Read available events from the source.

        Returns:
            List of raw event dictionaries. Each dict contains protocol-specific
            data that will be normalized by EventFactory into canonical Events.
        """
        ...

    @abstractmethod
    def source_name(self) -> str:
        """Return the human-readable name of this source.

        Returns:
            Source identifier string, e.g. 'telegram', 'signal', 'mqtt'.
        """
        ...
