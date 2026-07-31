"""
Event Bus Module.

In-memory event bus for publish-subscribe messaging within the Event Engine.
Supports subscribers, wildcard patterns, and priority queues.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import asyncio
import logging
import queue
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import UUID, uuid4

from app.core.event_context import EventContext
from app.core.event_exceptions import EventBusError

logger = logging.getLogger(__name__)


@dataclass
class Subscription:
    """
    Represents a subscription to the Event Bus.

    Attributes:
        id: Unique subscription identifier.
        subscriber_id: ID of the subscriber.
        event_types: Specific event types to subscribe to.
        patterns: Wildcard patterns to match.
        handler: The event handler callable.
        priority: Execution priority (higher = earlier).
        is_async: Whether the handler is async.
        is_active: Whether the subscription is active.
        created_at: When the subscription was created.
    """

    id: str
    subscriber_id: str
    event_types: Set[str] = field(default_factory=set)
    patterns: Set[str] = field(default_factory=set)
    handler: Callable = field(default=None)
    priority: int = 0
    is_async: bool = False
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def matches(self, event_type: str) -> bool:
        """
        Check if this subscription matches an event type.

        Args:
            event_type: The event type to check.

        Returns:
            True if the subscription matches.
        """
        if event_type in self.event_types:
            return True

        for pattern in self.patterns:
            if self._match_pattern(event_type, pattern):
                return True

        return False

    @staticmethod
    def _match_pattern(event_type: str, pattern: str) -> bool:
        """Match event type against a wildcard pattern."""
        if pattern == "*":
            return True
        if pattern.startswith("*."):
            return event_type.endswith(pattern[2:])
        if pattern.endswith(".*"):
            return event_type.startswith(pattern[:-2])
        return event_type == pattern


@dataclass
class BusMessage:
    """
    Message in the Event Bus queue.

    Attributes:
        id: Unique message identifier.
        event_type: The event type.
        event: The event payload.
        context: The event context.
        timestamp: When the message was queued.
        priority: Message priority.
    """

    id: str
    event_type: str
    event: Any
    context: EventContext
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    priority: int = 0


class EventBus:
    """
    In-memory event bus for publish-subscribe messaging.

    Provides a thread-safe message bus for event distribution.
    Supports multiple subscribers, wildcard patterns, priority queues,
    and both synchronous and asynchronous handlers.

    Attributes:
        subscriptions: Dictionary of event types to subscriptions.
        message_queue: Priority queue for async message processing.
        statistics: Bus statistics.

    Usage:
        >>> bus = EventBus()
        >>> 
        >>> def handle_radio(event, context):
        ...     print(f"Radio event: {event.title}")
        >>> 
        >>> bus.subscribe(
        ...     subscriber_id="radio-handler",
        ...     event_types=["radio.transmission"],
        ...     handler=handle_radio,
        ... )
        >>> 
        >>> bus.publish(
        ...     event_type="radio.transmission",
        ...     event=my_event,
        ...     context=my_context,
        ... )
    """

    def __init__(
        self,
        max_queue_size: int = 10000,
        default_priority: int = 0,
    ) -> None:
        """
        Initialize the Event Bus.

        Args:
            max_queue_size: Maximum size of the async message queue.
            default_priority: Default priority for queued messages.
        """
        self._lock = threading.RLock()
        self._subscriptions: Dict[str, List[Subscription]] = defaultdict(list)
        self._wildcard_subscriptions: List[Subscription] = []
        self._max_queue_size = max_queue_size
        self._default_priority = default_priority

        self._message_queue: queue.PriorityQueue = queue.PriorityQueue(
            maxsize=max_queue_size
        )
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False

        self._statistics = {
            "total_messages_published": 0,
            "total_messages_processed": 0,
            "total_messages_dropped": 0,
            "subscriber_count": 0,
        }

        logger.info("Event Bus initialized")

    @property
    def statistics(self) -> Dict[str, Any]:
        """Get bus statistics."""
        with self._lock:
            return {
                **self._statistics,
                "queue_size": self._message_queue.qsize(),
                "queue_max_size": self._max_queue_size,
                "active_subscriptions": sum(
                    1 for subs in self._subscriptions.values() for s in subs if s.is_active
                ),
            }

    def subscribe(
        self,
        subscriber_id: str,
        handler: Callable,
        event_types: Optional[List[str]] = None,
        patterns: Optional[List[str]] = None,
        priority: int = 0,
        is_async: bool = False,
    ) -> str:
        """
        Subscribe to event types.

        Args:
            subscriber_id: Unique identifier for the subscriber.
            handler: Callable that processes events.
            event_types: Specific event types to subscribe to.
            patterns: Wildcard patterns (e.g., "radio.*", "*.error").
            priority: Subscriber priority (higher = earlier execution).
            is_async: Whether the handler is asynchronous.

        Returns:
            The subscription ID.

        Raises:
            EventBusError: If subscription fails.
        """
        with self._lock:
            subscription_id = f"{subscriber_id}:{uuid4().hex[:8]}"

            subscription = Subscription(
                id=subscription_id,
                subscriber_id=subscriber_id,
                event_types=set(event_types or []),
                patterns=set(patterns or []),
                handler=handler,
                priority=priority,
                is_async=is_async,
            )

            if event_types:
                for event_type in event_types:
                    if not any(s.subscriber_id == subscriber_id for s in self._subscriptions[event_type]):
                        self._subscriptions[event_type].append(subscription)
                        self._subscriptions[event_type].sort(key=lambda s: s.priority, reverse=True)

            if patterns:
                has_wildcard = any(
                    p == "*" or p.startswith("*") or p.endswith("*")
                    for p in patterns
                )
                if has_wildcard and not any(s.subscriber_id == subscriber_id for s in self._wildcard_subscriptions):
                    self._wildcard_subscriptions.append(subscription)
                    self._wildcard_subscriptions.sort(key=lambda s: s.priority, reverse=True)

            self._statistics["subscriber_count"] += 1

            logger.info(
                f"Subscribed {subscriber_id} to events",
                extra={
                    "subscriber_id": subscriber_id,
                    "subscription_id": subscription_id,
                    "event_types": list(event_types or []),
                    "patterns": list(patterns or []),
                }
            )

            return subscription_id

    def unsubscribe(self, subscriber_id: str) -> int:
        """
        Unsubscribe a subscriber from all event types.

        Args:
            subscriber_id: The subscriber to unsubscribe.

        Returns:
            Number of subscriptions removed.
        """
        with self._lock:
            removed = 0

            for event_type, subs in self._subscriptions.items():
                new_subs = [s for s in subs if s.subscriber_id != subscriber_id]
                removed += len(subs) - len(new_subs)
                self._subscriptions[event_type] = new_subs

            self._wildcard_subscriptions = [
                s for s in self._wildcard_subscriptions
                if s.subscriber_id != subscriber_id
            ]

            if removed > 0:
                self._statistics["subscriber_count"] -= removed
                logger.info(f"Unsubscribed {subscriber_id}", extra={"removed": removed})

            return removed

    def publish(
        self,
        event_type: str,
        event: Any,
        context: Optional[EventContext] = None,
        priority: Optional[int] = None,
    ) -> int:
        """
        Publish an event to all matching subscribers.

        Synchronously dispatches to all matching handlers.

        Args:
            event_type: The event type string.
            event: The event payload.
            context: The event context.
            priority: Optional message priority.

        Returns:
            Number of subscribers that received the event.

        Raises:
            EventBusError: If publishing fails.
        """
        with self._lock:
            self._statistics["total_messages_published"] += 1

            context = context or EventContext(source="event-bus")

            subscribers = self._get_matching_subscriptions(event_type)

            if not subscribers:
                logger.debug(
                    f"No subscribers for event type: {event_type}",
                    extra={"event_type": event_type}
                )
                return 0

            delivered = 0

            for subscription in subscribers:
                try:
                    if subscription.is_async:
                        if asyncio.iscoroutinefunction(subscription.handler):
                            logger.warning(
                                f"Async handler called synchronously: {subscription.id}"
                            )

                    subscription.handler(event, context)
                    delivered += 1

                    logger.debug(
                        f"Delivered event to {subscription.subscriber_id}",
                        extra={
                            "subscription_id": subscription.id,
                            "event_type": event_type,
                        }
                    )

                except Exception as e:
                    logger.error(
                        f"Error delivering event to {subscription.subscriber_id}: {e}",
                        extra={
                            "subscription_id": subscription.id,
                            "event_type": event_type,
                            "error": str(e),
                        }
                    )

            return delivered

    def publish_async(
        self,
        event_type: str,
        event: Any,
        context: Optional[EventContext] = None,
        priority: Optional[int] = None,
    ) -> bool:
        """
        Publish an event to the async queue for processing.

        Non-blocking publish that queues the message for async processing.

        Args:
            event_type: The event type string.
            event: The event payload.
            context: The event context.
            priority: Optional message priority for ordering.

        Returns:
            True if the message was queued, False if queue is full.
        """
        with self._lock:
            priority = priority or self._default_priority

            message = BusMessage(
                id=str(uuid4()),
                event_type=event_type,
                event=event,
                context=context or EventContext(source="event-bus"),
                priority=priority,
            )

            try:
                self._message_queue.put_nowait(message)
                self._statistics["total_messages_published"] += 1

                logger.debug(
                    f"Queued async message: {event_type}",
                    extra={"message_id": message.id, "queue_size": self._message_queue.qsize()}
                )

                return True

            except queue.Full:
                logger.warning(
                    f"Message queue full, dropping message: {event_type}",
                    extra={"event_type": event_type}
                )
                self._statistics["total_messages_dropped"] += 1
                return False

    def start_async_processing(self) -> None:
        """
        Start the async message processing worker.

        Creates a background thread that processes queued messages.
        """
        if self._running:
            logger.warning("Async processing already running")
            return

        self._running = True
        self._worker_thread = threading.Thread(
            target=self._process_messages,
            daemon=True,
            name="EventBusWorker"
        )
        self._worker_thread.start()

        logger.info("Started async message processing")

    def stop_async_processing(self) -> None:
        """
        Stop the async message processing worker.
        """
        if not self._running:
            return

        self._running = False

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5.0)

        self._worker_thread = None

        logger.info("Stopped async message processing")

    def _process_messages(self) -> None:
        """Background worker that processes queued messages."""
        while self._running:
            try:
                message = self._message_queue.get(timeout=1.0)

                try:
                    self.publish(
                        event_type=message.event_type,
                        event=message.event,
                        context=message.context,
                    )
                    self._statistics["total_messages_processed"] += 1

                finally:
                    self._message_queue.task_done()

            except queue.Empty:
                continue

            except Exception as e:
                logger.error(f"Error processing message: {e}")

    def _get_matching_subscriptions(self, event_type: str) -> List[Subscription]:
        """
        Get all subscriptions matching an event type.

        Args:
            event_type: The event type to match.

        Returns:
            List of matching subscriptions sorted by priority.
        """
        subscriptions = []

        if event_type in self._subscriptions:
            subscriptions.extend(
                s for s in self._subscriptions[event_type] if s.is_active
            )

        for subscription in self._wildcard_subscriptions:
            if subscription.is_active and subscription.matches(event_type):
                if subscription not in subscriptions:
                    subscriptions.append(subscription)

        return sorted(subscriptions, key=lambda s: s.priority, reverse=True)

    def get_subscription_count(self, event_type: Optional[str] = None) -> int:
        """
        Get the number of subscriptions.

        Args:
            event_type: Optional event type to filter by.

        Returns:
            Number of subscriptions.
        """
        with self._lock:
            if event_type:
                return len([
                    s for s in self._subscriptions.get(event_type, [])
                    if s.is_active
                ])
            return sum(
                1 for subs in self._subscriptions.values()
                for s in subs if s.is_active
            ) + len([s for s in self._wildcard_subscriptions if s.is_active])

    def get_subscribers(self, event_type: Optional[str] = None) -> List[str]:
        """
        Get list of subscriber IDs.

        Args:
            event_type: Optional event type to filter by.

        Returns:
            List of subscriber IDs.
        """
        with self._lock:
            subscribers = set()

            if event_type:
                for sub in self._subscriptions.get(event_type, []):
                    if sub.is_active:
                        subscribers.add(sub.subscriber_id)
            else:
                for subs in self._subscriptions.values():
                    for sub in subs:
                        if sub.is_active:
                            subscribers.add(sub.subscriber_id)
                for sub in self._wildcard_subscriptions:
                    if sub.is_active:
                        subscribers.add(sub.subscriber_id)

            return list(subscribers)

    def clear(self) -> None:
        """Clear all subscriptions and queued messages."""
        with self._lock:
            self._subscriptions.clear()
            self._wildcard_subscriptions.clear()

            while not self._message_queue.empty():
                try:
                    self._message_queue.get_nowait()
                except queue.Empty:
                    break

            self._statistics = {
                "total_messages_published": 0,
                "total_messages_processed": 0,
                "total_messages_dropped": 0,
                "subscriber_count": 0,
            }

            logger.info("Event Bus cleared")

    def to_dict(self) -> Dict[str, Any]:
        """Convert bus state to dictionary."""
        with self._lock:
            return {
                "subscriptions": {
                    et: [
                        {
                            "id": s.id,
                            "subscriber_id": s.subscriber_id,
                            "priority": s.priority,
                            "is_async": s.is_async,
                            "is_active": s.is_active,
                        }
                        for s in subs
                    ]
                    for et, subs in self._subscriptions.items()
                },
                "statistics": self.statistics,
            }
