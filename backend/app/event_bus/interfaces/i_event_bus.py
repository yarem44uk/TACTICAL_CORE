from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.event.event_types import EventType
    from backend.app.event_bus.subscription import Subscription


class IEventBus(ABC):
    """Event bus interface."""

    @abstractmethod
    def subscribe(
        self, event_type: "EventType", callback: callable
    ) -> "Subscription": ...

    @abstractmethod
    def unsubscribe(self, subscription: "Subscription") -> bool: ...

    @abstractmethod
    def publish(self, event: object) -> int: ...

    @abstractmethod
    def clear(self) -> None: ...

    @abstractmethod
    def subscriber_count(self) -> int: ...

    @abstractmethod
    def get_subscribers(self, event_type: "EventType") -> list["Subscription"]: ...
