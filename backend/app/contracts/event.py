"""
Event Contracts.

Interfaces for event system.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID


class IEventPublisher(ABC):
    """
    Interface for event publishing.
    """

    @abstractmethod
    def publish(
        self,
        event_data: Dict[str, Any],
        correlation_id: Optional[str] = None,
        source: str = "system",
    ) -> UUID:
        """Publish an event and return its ID."""
        pass

    @abstractmethod
    def publish_many(
        self,
        events: List[Dict[str, Any]],
        correlation_id: Optional[str] = None,
    ) -> List[UUID]:
        """Publish multiple events."""
        pass


class IEventSubscriber(ABC):
    """
    Interface for event subscription.
    """

    @abstractmethod
    def subscribe(
        self,
        handler: Callable,
        event_types: Optional[List[str]] = None,
        patterns: Optional[List[str]] = None,
        priority: int = 0,
    ) -> str:
        """Subscribe to events and return subscription ID."""
        pass

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from events."""
        pass

    @abstractmethod
    def is_subscribed(self, subscription_id: str) -> bool:
        """Check if subscription is active."""
        pass



class IEventBus(ABC):
    """
    Interface for event bus message distribution.
    """

    @abstractmethod
    def subscribe(
        self,
        subscriber_id: str,
        handler: Callable,
        event_types: Optional[List[str]] = None,
        patterns: Optional[List[str]] = None,
        priority: int = 0,
        is_async: bool = False,
    ) -> str:
        """Subscribe to events and return subscription ID."""
        pass

    @abstractmethod
    def unsubscribe(self, subscriber_id: str) -> bool:
        """Unsubscribe from events."""
        pass

    @abstractmethod
    def publish(
        self,
        event_type: str,
        event: Any,
        context: Optional[Any] = None,
    ) -> int:
        """Publish an event to matching subscribers."""
        pass

    @abstractmethod
    def get_subscribers(self, event_type: Optional[str] = None) -> List[str]:
        """Get list of subscriber IDs."""
        pass
