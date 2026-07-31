"""
Messaging Contracts.

Interfaces for messaging systems.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional


class IMessageSource(ABC):
    """
    Interface for incoming messages.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Source identifier."""
        pass

    @abstractmethod
    def connect(self) -> None:
        """Connect to message source."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from message source."""
        pass

    @abstractmethod
    def receive(self) -> Optional[Dict[str, Any]]:
        """Receive next message. Returns None if no message."""
        pass


class IMessageSink(ABC):
    """
    Interface for outgoing messages.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Sink identifier."""
        pass

    @abstractmethod
    def send(
        self,
        message: str,
        recipient: str,
        attachments: Optional[List[str]] = None,
    ) -> bool:
        """Send a message."""
        pass
