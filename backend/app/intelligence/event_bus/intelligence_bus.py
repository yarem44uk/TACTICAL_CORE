"""Intelligence Bus Module.

Internal pub/sub event bus for Intelligence Core.

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

from app.intelligence.event_bus.subscriptions import (
    Subscription,
    SubscriptionManager,
    SubscriptionStatus,
)
from app.intelligence.event_bus.patterns import PatternMatcher, WildcardMatcher, MatchResult
from app.intelligence.event_bus.routing import EventRouter, RoutingStrategy


@dataclass
class BusConfig:
    """Configuration for IntelligenceBus.

    Attributes:
        enable_dead_letter_queue: Store failed events.
        max_queue_size: Maximum event queue size.
        worker_threads: Number of worker threads.
        replay_enabled: Enable event replay.
        pattern_matcher: Pattern matcher to use.
    """

    enable_dead_letter_queue: bool = True
    max_queue_size: int = 10000
    worker_threads: int = 4
    replay_enabled: bool = True
    pattern_matcher: Optional[PatternMatcher] = None


class DeadLetterEvent:
    """Event that failed processing.

    Attributes:
        event: Original event.
        error: Error message.
        failed_at: When failure occurred.
        retry_count: Number of retry attempts.
    """

    def __init__(
        self,
        event: Any,
        error: str,
        failed_at: Optional[datetime] = None,
        retry_count: int = 0,
    ) -> None:
        """Initialize DeadLetterEvent.

        Args:
            event: Original event.
            error: Error message.
            failed_at: Failure timestamp.
            retry_count: Retry count.
        """
        self.event = event
        self.error = error
        self.failed_at = failed_at or datetime.now(timezone.utc)
        self.retry_count = retry_count


class IntelligenceBus:
    """Enhanced event bus for Intelligence Core.

    Provides in-memory pub/sub with:
    - Wildcard pattern support
    - Priority-based delivery
    - Async and sync handlers
    - Dead letter queue
    - Event replay
    - Event routing

    Attributes:
        config: Bus configuration.
        subscriptions: Subscription manager.
        router: Event router.
    """

    def __init__(
        self,
        config: Optional[BusConfig] = None,
    ) -> None:
        """Initialize the IntelligenceBus.

        Args:
            config: Bus configuration.
        """
        self.config = config or BusConfig()
        self._logger = logging.getLogger(f"{__name__}.IntelligenceBus")
        self.subscriptions = SubscriptionManager()
        self.router = EventRouter()
        self._pattern_matcher = self.config.pattern_matcher or WildcardMatcher()
        self._event_queue: queue.Queue = queue.Queue(maxsize=self.config.max_queue_size)
        self._dead_letter_queue: List[DeadLetterEvent] = []
        self._processing = False
        self._workers: List[threading.Thread] = []
        self._lock = threading.Lock()

        # Replay support
        self._replay_log: List[Any] = []
        self._max_replay_events = 10000

    def subscribe(
        self,
        pattern: str,
        handler: Callable,
        subscriber_id: Optional[str] = None,
        priority: int = 0,
        event_types: Optional[Set[str]] = None,
    ) -> Subscription:
        """Subscribe to events matching a pattern.

        Args:
            pattern: Wildcard pattern to match.
            handler: Event handler callable.
            subscriber_id: Subscriber identifier.
            priority: Handler priority (higher = earlier).
            event_types: Specific event types.

        Returns:
            Subscription instance.
        """
        sub_id = subscriber_id or str(uuid4())

        # Detect async handler
        is_async = asyncio.iscoroutinefunction(handler)

        subscription = self.subscriptions.create(
            subscriber_id=sub_id,
            patterns={pattern},
            handler=handler,
            priority=priority,
            is_async=is_async,
            event_types=event_types,
        )

        self._logger.info(
            f"New subscription: {subscription.id} (pattern={pattern}, "
            f"priority={priority}, async={is_async})"
        )

        return subscription

    def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from events.

        Args:
            subscription_id: Subscription identifier.

        Returns:
            True if unsubscribed, False if not found.
        """
        result = self.subscriptions.delete(subscription_id)
        if result:
            self._logger.info(f"Unsubscribed: {subscription_id}")
        return result

    def subscribe_typed(
        self,
        event_types: Set[str],
        handler: Callable,
        subscriber_id: Optional[str] = None,
        priority: int = 0,
    ) -> Subscription:
        """Subscribe to specific event types.

        Args:
            event_types: Set of event types.
            handler: Event handler callable.
            subscriber_id: Subscriber identifier.
            priority: Handler priority.

        Returns:
            Subscription instance.
        """
        return self.subscribe(
            pattern="*",
            handler=handler,
            subscriber_id=subscriber_id,
            priority=priority,
            event_types=event_types,
        )

    async def publish(
        self,
        event: Any,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
    ) -> None:
        """Publish an event to subscribers.

        Args:
            event: Event to publish.
            event_type: Event type (extracted if not provided).
            source: Event source (extracted if not provided).
        """
        # Extract event type and source
        if event_type is None:
            event_type = getattr(event, "event_type", str(event))
        if source is None:
            source = getattr(event, "source", "unknown")

        # Store for replay
        if self.config.replay_enabled:
            with self._lock:
                self._replay_log.append(event)
                if len(self._replay_log) > self._max_replay_events:
                    self._replay_log.pop(0)

        # Find matching subscriptions
        matches = self.subscriptions.find_matching(event_type)

        if not matches:
            self._logger.debug(f"No subscribers for {event_type}")
            return

        self._logger.debug(
            f"Publishing {event_type} from {source} to {len(matches)} subscribers"
        )

        # Dispatch to handlers
        errors: List[str] = []
        for subscription in matches:
            try:
                if subscription.is_async:
                    if asyncio.iscoroutinefunction(subscription.handler):
                        await subscription.handler(event)
                    else:
                        # Run sync handler in executor
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, subscription.handler, event)
                else:
                    subscription.handler(event)

                subscription.mark_executed(success=True)

            except Exception as e:
                error_msg = f"Handler {subscription.id} failed: {e}"
                self._logger.error(error_msg)
                errors.append(error_msg)
                subscription.mark_executed(success=False)

                # Add to dead letter queue
                if self.config.enable_dead_letter_queue:
                    self._dead_letter_queue.append(
                        DeadLetterEvent(event, str(e))
                    if len(self._dead_letter_queue) > 1000:
                        self._dead_letter_queue.pop(0)

        # Log if any errors occurred
        if errors:
            self._logger.warning(
                f"Event {event_type} published with {len(errors)} errors"
            )

    def publish_sync(
        self,
        event: Any,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
    ) -> None:
        """Synchronous publish wrapper.

        Args:
            event: Event to publish.
            event_type: Event type.
            source: Event source.
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    self.publish(event, event_type, source)
                )
            finally:
                loop.close()
        except RuntimeError:
            # No event loop, create task
            asyncio.get_event_loop().run_until_complete(
                self.publish(event, event_type, source)
            )

    async def replay(
        self,
        from_index: int = 0,
        to_index: Optional[int] = None,
    ) -> List[Any]:
        """Replay events from the replay log.

        Args:
            from_index: Starting index.
            to_index: Ending index (None = all).

        Returns:
            List of replayed events.
        """
        if not self.config.replay_enabled:
            self._logger.warning("Replay is disabled")
            return []

        with self._lock:
            if to_index is None:
                to_index = len(self._replay_log)

            events = self._replay_log[from_index:to_index]

        self._logger.info(f"Replaying {len(events)} events")

        for event in events:
            event_type = getattr(event, "event_type", None)
            source = getattr(event, "source", None)
            await self.publish(event, event_type, source)

        return events

    def get_dead_letter_events(self) -> List[DeadLetterEvent]:
        """Get all dead letter events.

        Returns:
            List of failed events.
        """
        return self._dead_letter_queue.copy()

    def clear_dead_letter_queue(self) -> int:
        """Clear the dead letter queue.

        Returns:
            Number of events cleared.
        """
        count = len(self._dead_letter_queue)
        self._dead_letter_queue.clear()
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get bus statistics.

        Returns:
            Dictionary with statistics.
        """
        sub_stats = self.subscriptions.get_stats()
        return {
            "subscriptions": sub_stats,
            "dead_letter_queue_size": len(self._dead_letter_queue),
            "replay_log_size": len(self._replay_log),
            "is_processing": self._processing,
        }

    async def shutdown(self) -> None:
        """Shutdown the event bus.

        Stops all workers and clears queues.
        """
        self._logger.info("Shutting down IntelligenceBus")
        self._processing = False

        # Wait for workers to finish
        for worker in self._workers:
            worker.join(timeout=5.0)

        self._workers.clear()
        self._logger.info("IntelligenceBus shutdown complete")
