"""
Event Dispatcher Module.

Routes events to registered subscribers with support for sync/async handlers,
priority queues, and exception isolation.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import asyncio
import concurrent.futures
import logging
import threading
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import UUID
from concurrent.futures import ThreadPoolExecutor, Future

from app.core.event_context import EventContext
from app.core.event_exceptions import EventDispatchError, SubscriberError
from app.core.event_registry import EventRegistry, SubscriberInfo

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    """
    Result of a single dispatcher operation.

    Attributes:
        subscriber_id: The subscriber that was dispatched to.
        success: Whether dispatch succeeded.
        error: Error message if dispatch failed.
        execution_time_ms: Time taken to execute the handler.
        is_async: Whether the handler was async.
    """

    subscriber_id: str
    success: bool = True
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    is_async: bool = False


@dataclass
class DispatcherStatistics:
    """
    Dispatcher runtime statistics.

    Attributes:
        total_dispatches: Total number of dispatches.
        successful_dispatches: Number of successful dispatches.
        failed_dispatches: Number of failed dispatches.
        total_execution_time_ms: Total time spent in handlers.
        average_execution_time_ms: Average handler execution time.
        concurrent_dispatches: Current number of concurrent dispatches.
    """

    total_dispatches: int = 0
    successful_dispatches: int = 0
    failed_dispatches: int = 0
    total_execution_time_ms: float = 0.0
    average_execution_time_ms: float = 0.0
    concurrent_dispatches: int = 0
    last_dispatch_time: Optional[datetime] = None


class EventDispatcher:
    """
    Event dispatcher for routing events to subscribers.

    Handles both synchronous and asynchronous event delivery.
    Supports parallel execution, priority ordering, and exception isolation.

    Attributes:
        registry: The Event Registry for subscriber lookup.
        max_workers: Maximum parallel workers for async dispatch.
        enable_parallel: Whether to enable parallel dispatch.
        statistics: Runtime statistics.

    Usage:
        >>> dispatcher = EventDispatcher(registry)
        >>> 
        >>> results = dispatcher.dispatch(
        ...     event=my_event,
        ...     context=my_context,
        ...     event_type="radio.transmission",
        ... )
        >>> 
        >>> for result in results:
        ...     print(f"{result.subscriber_id}: {'OK' if result.success else result.error}")
    """

    def __init__(
        self,
        registry: EventRegistry,
        max_workers: int = 10,
        enable_parallel: bool = True,
        executor: Optional[ThreadPoolExecutor] = None,
    ) -> None:
        """
        Initialize the Event Dispatcher.

        Args:
            registry: The Event Registry for subscriber lookup.
            max_workers: Maximum number of parallel workers.
            enable_parallel: Whether to enable parallel execution.
            executor: Optional custom thread pool executor.
        """
        self._registry = registry
        self._max_workers = max_workers
        self._enable_parallel = enable_parallel
        self._executor = executor

        self._lock = threading.RLock()
        self._active_futures: Dict[str, Future] = {}
        self._statistics = DispatcherStatistics()

        logger.info(
            "Event Dispatcher initialized",
            extra={"max_workers": max_workers, "parallel": enable_parallel}
        )

    @property
    def statistics(self) -> DispatcherStatistics:
        """Get dispatcher statistics."""
        with self._lock:
            return DispatcherStatistics(
                total_dispatches=self._statistics.total_dispatches,
                successful_dispatches=self._statistics.successful_dispatches,
                failed_dispatches=self._statistics.failed_dispatches,
                total_execution_time_ms=self._statistics.total_execution_time_ms,
                average_execution_time_ms=self._statistics.average_execution_time_ms,
                concurrent_dispatches=len(self._active_futures),
                last_dispatch_time=self._statistics.last_dispatch_time,
            )

    def dispatch(
        self,
        event: Any,
        context: EventContext,
        event_type: str,
    ) -> List[DispatchResult]:
        """
        Dispatch an event to all matching subscribers.

        Args:
            event: The event to dispatch.
            context: The event context.
            event_type: The event type string.

        Returns:
            List of DispatchResult for each subscriber.
        """
        start_time = datetime.now(timezone.utc)

        subscribers = self._registry.get_subscribers_for_event(event_type)

        if not subscribers:
            logger.debug(
                f"No subscribers for event type: {event_type}",
                extra={"event_type": event_type}
            )
            return []

        logger.info(
            f"Dispatching event to {len(subscribers)} subscribers",
            extra={
                "event_type": event_type,
                "subscriber_count": len(subscribers),
            }
        )

        results = []

        if self._enable_parallel and len(subscribers) > 1:
            results = self._dispatch_parallel(event, context, subscribers)
        else:
            results = self._dispatch_sequential(event, context, subscribers)

        with self._lock:
            self._statistics.total_dispatches += len(subscribers)
            self._statistics.last_dispatch_time = datetime.now(timezone.utc)

            for result in results:
                if result.success:
                    self._statistics.successful_dispatches += 1
                else:
                    self._statistics.failed_dispatches += 1

                self._statistics.total_execution_time_ms += result.execution_time_ms

            if self._statistics.total_dispatches > 0:
                self._statistics.average_execution_time_ms = (
                    self._statistics.total_execution_time_ms /
                    self._statistics.total_dispatches
                )

        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        logger.info(
            f"Event dispatched in {execution_time:.2f}ms",
            extra={
                "event_type": event_type,
                "execution_time_ms": execution_time,
                "success_count": sum(1 for r in results if r.success),
                "failure_count": sum(1 for r in results if not r.success),
            }
        )

        return results

    def dispatch_to_handler(
        self,
        event: Any,
        context: EventContext,
        event_type: str,
    ) -> Optional[Any]:
        """
        Dispatch to registered handlers instead of subscribers.

        Args:
            event: The event to process.
            context: The event context.
            event_type: The event type string.

        Returns:
            Result from the handler, or None.
        """
        handlers = self._registry.get_handlers_for_event(event_type)

        if not handlers:
            return None

        result = None
        for handler_info in handlers:
            try:
                handler_result = handler_info.handler(event, context)
                if handler_result is not None:
                    result = handler_result
            except Exception as e:
                logger.error(
                    f"Handler {handler_info.id} failed: {e}",
                    extra={"handler_id": handler_info.id, "error": str(e)}
                )

        return result

    def _dispatch_sequential(
        self,
        event: Any,
        context: EventContext,
        subscribers: List[SubscriberInfo],
    ) -> List[DispatchResult]:
        """
        Dispatch events sequentially to subscribers.

        Args:
            event: The event to dispatch.
            context: The event context.
            subscribers: List of subscribers.

        Returns:
            List of dispatch results.
        """
        results = []

        for subscriber in subscribers:
            result = self._execute_handler(event, context, subscriber)
            results.append(result)

            self._update_subscriber_stats(subscriber, result)

        return results

    def _dispatch_parallel(
        self,
        event: Any,
        context: EventContext,
        subscribers: List[SubscriberInfo],
    ) -> List[DispatchResult]:
        """
        Dispatch events in parallel to subscribers.

        Args:
            event: The event to dispatch.
            context: The event context.
            subscribers: List of subscribers.

        Returns:
            List of dispatch results.
        """
        executor = self._executor or ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="EventDispatcher"
        )

        futures = {}
        for subscriber in subscribers:
            future = executor.submit(
                self._execute_handler,
                event,
                context,
                subscriber,
            )
            futures[future] = subscriber

        results = []
        for future in concurrent.futures.as_completed(futures):
            subscriber = futures[future]
            try:
                result = future.result()
                results.append(result)
                self._update_subscriber_stats(subscriber, result)
            except Exception as e:
                logger.error(
                    f"Future execution failed for {subscriber.id}: {e}"
                )
                results.append(DispatchResult(
                    subscriber_id=subscriber.id,
                    success=False,
                    error=str(e),
                ))

        return results

    def _execute_handler(
        self,
        event: Any,
        context: EventContext,
        subscriber: SubscriberInfo,
    ) -> DispatchResult:
        """
        Execute a single subscriber handler.

        Args:
            event: The event to dispatch.
            context: The event context.
            subscriber: The subscriber info.

        Returns:
            DispatchResult for this subscriber.
        """
        start_time = datetime.now(timezone.utc)

        try:
            if subscriber.is_async:
                if asyncio.iscoroutinefunction(subscriber.handler):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        result = loop.run_until_complete(
                            subscriber.handler(event, context)
                        )
                    finally:
                        loop.close()
                else:
                    result = subscriber.handler(event, context)
            else:
                result = subscriber.handler(event, context)

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            logger.debug(
                f"Handler executed: {subscriber.id}",
                extra={
                    "subscriber_id": subscriber.id,
                    "execution_time_ms": execution_time,
                }
            )

            return DispatchResult(
                subscriber_id=subscriber.id,
                success=True,
                execution_time_ms=execution_time,
                is_async=subscriber.is_async,
            )

        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            logger.error(
                f"Handler execution failed: {subscriber.id}",
                extra={
                    "subscriber_id": subscriber.id,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )

            return DispatchResult(
                subscriber_id=subscriber.id,
                success=False,
                error=str(e),
                execution_time_ms=execution_time,
                is_async=subscriber.is_async,
            )

    def _update_subscriber_stats(
        self,
        subscriber: SubscriberInfo,
        result: DispatchResult,
    ) -> None:
        """
        Update subscriber execution statistics.

        Args:
            subscriber: The subscriber info.
            result: The dispatch result.
        """
        self._registry._subscribers[subscriber.id].update_execution(result.success)

    def dispatch_to_plugins(
        self,
        event: Any,
        context: EventContext,
        event_type: str,
    ) -> List[str]:
        """
        Dispatch to registered plugins that subscribe to this event type.

        Args:
            event: The event to dispatch.
            context: The event context.
            event_type: The event type string.

        Returns:
            List of plugin IDs that were notified.
        """
        notified_plugins = []

        plugins = self._registry.plugins
        for plugin_id, plugin in plugins.items():
            if not plugin.is_active:
                continue

            if event_type in plugin.subscriptions:
                try:
                    logger.debug(
                        f"Notifying plugin: {plugin_id}",
                        extra={"plugin_id": plugin_id, "event_type": event_type}
                    )
                    notified_plugins.append(plugin_id)

                except Exception as e:
                    logger.error(
                        f"Failed to notify plugin {plugin_id}: {e}",
                        extra={"plugin_id": plugin_id, "error": str(e)}
                    )

        return notified_plugins

    def get_subscribers_for_event(self, event_type: str) -> List[SubscriberInfo]:
        """
        Get all subscribers for an event type.

        Args:
            event_type: The event type.

        Returns:
            List of SubscriberInfo sorted by priority.
        """
        return self._registry.get_subscribers_for_event(event_type)

    def get_active_count(self) -> int:
        """
        Get the number of active dispatch operations.

        Returns:
            Number of concurrent dispatch operations.
        """
        with self._lock:
            return len(self._active_futures)

    def cancel_all(self) -> int:
        """
        Cancel all pending dispatch operations.

        Returns:
            Number of operations cancelled.
        """
        with self._lock:
            cancelled = 0
            for future in self._active_futures:
                if future.cancel():
                    cancelled += 1
            self._active_futures.clear()
            return cancelled

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert dispatcher state to dictionary.

        Returns:
            Dictionary representation of the dispatcher.
        """
        stats = self.statistics
        return {
            "max_workers": self._max_workers,
            "enable_parallel": self._enable_parallel,
            "statistics": {
                "total_dispatches": stats.total_dispatches,
                "successful_dispatches": stats.successful_dispatches,
                "failed_dispatches": stats.failed_dispatches,
                "total_execution_time_ms": stats.total_execution_time_ms,
                "average_execution_time_ms": stats.average_execution_time_ms,
                "concurrent_dispatches": stats.concurrent_dispatches,
            },
        }
