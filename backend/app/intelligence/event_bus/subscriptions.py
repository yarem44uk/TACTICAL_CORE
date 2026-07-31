"""Subscription Management Module.

Handles event bus subscription lifecycle and management.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import UUID, uuid4


class SubscriptionStatus(str, Enum):
    """Subscription status values."""

    ACTIVE = "active"
    PAUSED = "paused"
    TERMINATED = "terminated"


@dataclass
class Subscription:
    """Represents a subscription to the Event Bus.

    Attributes:
        id: Unique subscription identifier.
        subscriber_id: ID of the subscriber.
        event_types: Specific event types to subscribe to.
        patterns: Wildcard patterns to match.
        handler: The event handler callable.
        priority: Execution priority (higher = earlier).
        is_async: Whether the handler is async.
        status: Current subscription status.
        created_at: When subscription was created.
        last_executed: Last execution timestamp.
        execution_count: Number of times handler executed.
        error_count: Number of handler errors.
    """

    id: str
    subscriber_id: str
    event_types: Set[str] = field(default_factory=set)
    patterns: Set[str] = field(default_factory=set)
    handler: Callable = field(default=None)
    priority: int = 0
    is_async: bool = False
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_executed: Optional[datetime] = None
    execution_count: int = 0
    error_count: int = 0

    def matches_event(self, event_type: str) -> bool:
        """Check if subscription matches an event type.

        Args:
            event_type: Event type to check.

        Returns:
            True if subscription matches.
        """
        if self.event_types and event_type in self.event_types:
            return True
        return False

    def mark_executed(self, success: bool = True) -> None:
        """Mark subscription as executed.

        Args:
            success: Whether execution was successful.
        """
        self.last_executed = datetime.now(timezone.utc)
        self.execution_count += 1
        if not success:
            self.error_count += 1

    def pause(self) -> None:
        """Pause the subscription."""
        self.status = SubscriptionStatus.PAUSED

    def resume(self) -> None:
        """Resume the subscription."""
        self.status = SubscriptionStatus.ACTIVE

    def terminate(self) -> None:
        """Terminate the subscription."""
        self.status = SubscriptionStatus.TERMINATED

    @property
    def is_active(self) -> bool:
        """Check if subscription is active.

        Returns:
            True if status is ACTIVE.
        """
        return self.status == SubscriptionStatus.ACTIVE

    @property
    def error_rate(self) -> float:
        """Calculate error rate.

        Returns:
            Error rate as percentage.
        """
        if self.execution_count == 0:
            return 0.0
        return (self.error_count / self.execution_count) * 100


class SubscriptionManager:
    """Manages event bus subscriptions.

    Provides CRUD operations for subscriptions and
    subscription discovery by pattern or subscriber.

    Attributes:
        subscriptions: All active subscriptions.
    """

    def __init__(self) -> None:
        """Initialize the SubscriptionManager."""
        self._subscriptions: Dict[str, Subscription] = {}
        self._by_subscriber: Dict[str, Set[str]] = {}
        self._by_pattern: Dict[str, Set[str]] = {}

    def create(
        self,
        subscriber_id: str,
        event_types: Optional[Set[str]] = None,
        patterns: Optional[Set[str]] = None,
        handler: Optional[Callable] = None,
        priority: int = 0,
        is_async: bool = False,
    ) -> Subscription:
        """Create a new subscription.

        Args:
            subscriber_id: Subscriber identifier.
            event_types: Event types to subscribe to.
            patterns: Wildcard patterns.
            handler: Event handler callable.
            priority: Execution priority.
            is_async: Whether handler is async.

        Returns:
            Created subscription.
        """
        import asyncio
        is_async = asyncio.iscoroutinefunction(handler) if handler else is_async

        subscription = Subscription(
            id=str(uuid4()),
            subscriber_id=subscriber_id,
            event_types=event_types or set(),
            patterns=patterns or set(),
            handler=handler,
            priority=priority,
            is_async=is_async,
        )

        self._subscriptions[subscription.id] = subscription

        # Index by subscriber
        if subscriber_id not in self._by_subscriber:
            self._by_subscriber[subscriber_id] = set()
        self._by_subscriber[subscriber_id].add(subscription.id)

        # Index by pattern
        for pattern in subscription.patterns:
            if pattern not in self._by_pattern:
                self._by_pattern[pattern] = set()
            self._by_pattern[pattern].add(subscription.id)

        return subscription

    def get(self, subscription_id: str) -> Optional[Subscription]:
        """Get subscription by ID.

        Args:
            subscription_id: Subscription identifier.

        Returns:
            Subscription if found, None otherwise.
        """
        return self._subscriptions.get(subscription_id)

    def get_by_subscriber(self, subscriber_id: str) -> List[Subscription]:
        """Get all subscriptions for a subscriber.

        Args:
            subscriber_id: Subscriber identifier.

        Returns:
            List of subscriptions.
        """
        sub_ids = self._by_subscriber.get(subscriber_id, set())
        return [self._subscriptions[sid] for sid in sub_ids if sid in self._subscriptions]

    def get_by_pattern(self, pattern: str) -> List[Subscription]:
        """Get all subscriptions matching a pattern.

        Args:
            pattern: Pattern to match.

        Returns:
            List of matching subscriptions.
        """
        sub_ids = self._by_pattern.get(pattern, set())
        return [self._subscriptions[sid] for sid in sub_ids if sid in self._subscriptions]

    def get_active(self) -> List[Subscription]:
        """Get all active subscriptions.

        Returns:
            List of active subscriptions.
        """
        return [s for s in self._subscriptions.values() if s.is_active]

    def find_matching(
        self,
        event_type: str,
        patterns: Optional[List[str]] = None,
    ) -> List[Subscription]:
        """Find subscriptions matching an event.

        Args:
            event_type: Event type to match.
            patterns: Optional patterns to match.

        Returns:
            List of matching subscriptions sorted by priority.
        """
        matches: List[Subscription] = []

        for sub in self._subscriptions.values():
            if not sub.is_active:
                continue

            # Check event type
            if sub.event_types and event_type not in sub.event_types:
                continue

            # Check patterns
            if patterns:
                pattern_match = False
                for pattern in patterns:
                    if pattern in sub.patterns:
                        pattern_match = True
                        break
                if not pattern_match:
                    continue

            matches.append(sub)

        # Sort by priority (descending)
        matches.sort(key=lambda s: s.priority, reverse=True)
        return matches

    def delete(self, subscription_id: str) -> bool:
        """Delete a subscription.

        Args:
            subscription_id: Subscription identifier.

        Returns:
            True if deleted, False if not found.
        """
        subscription = self._subscriptions.pop(subscription_id, None)
        if subscription is None:
            return False

        # Remove from subscriber index
        if subscription.subscriber_id in self._by_subscriber:
            self._by_subscriber[subscription.subscriber_id].discard(subscription_id)

        # Remove from pattern index
        for pattern in subscription.patterns:
            if pattern in self._by_pattern:
                self._by_pattern[pattern].discard(subscription_id)

        return True

    def delete_by_subscriber(self, subscriber_id: str) -> int:
        """Delete all subscriptions for a subscriber.

        Args:
            subscriber_id: Subscriber identifier.

        Returns:
            Number of subscriptions deleted.
        """
        sub_ids = self._by_subscriber.pop(subscriber_id, set())
        count = 0
        for sid in sub_ids:
            if sid in self._subscriptions:
                del self._subscriptions[sid]
                count += 1

        # Clean up pattern index
        for pattern, sids in self._by_pattern.items():
            sids -= sub_ids

        return count

    def pause_by_subscriber(self, subscriber_id: str) -> int:
        """Pause all subscriptions for a subscriber.

        Args:
            subscriber_id: Subscriber identifier.

        Returns:
            Number of subscriptions paused.
        """
        count = 0
        for sub in self.get_by_subscriber(subscriber_id):
            sub.pause()
            count += 1
        return count

    def resume_by_subscriber(self, subscriber_id: str) -> int:
        """Resume all subscriptions for a subscriber.

        Args:
            subscriber_id: Subscriber identifier.

        Returns:
            Number of subscriptions resumed.
        """
        count = 0
        for sub in self.get_by_subscriber(subscriber_id):
            sub.resume()
            count += 1
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get subscription statistics.

        Returns:
            Dictionary with statistics.
        """
        active = self.get_active()
        return {
            "total_subscriptions": len(self._subscriptions),
            "active_subscriptions": len(active),
            "paused_subscriptions": sum(1 for s in self._subscriptions.values() if s.status == SubscriptionStatus.PAUSED),
            "terminated_subscriptions": sum(1 for s in self._subscriptions.values() if s.status == SubscriptionStatus.TERMINATED),
            "total_executions": sum(s.execution_count for s in self._subscriptions.values()),
            "total_errors": sum(s.error_count for s in self._subscriptions.values()),
        }
