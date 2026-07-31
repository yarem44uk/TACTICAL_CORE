"""
Event Registry Module.

Central registry for tracking plugins, handlers, subscribers, and event types
registered with the Event Engine.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import UUID, uuid4


@dataclass
class SubscriberInfo:
    """
    Information about a registered subscriber.

    Attributes:
        id: Unique subscriber identifier.
        name: Human-readable subscriber name.
        handler: The handler callable.
        event_types: Event types this subscriber listens to.
        patterns: Subscription patterns (e.g., "radio.*", "*.error").
        priority: Subscriber priority (higher = executed first).
        is_async: Whether the handler is asynchronous.
        is_active: Whether the subscriber is currently active.
        created_at: When the subscriber was registered.
        last_executed: When the subscriber last processed an event.
        execution_count: Number of events processed.
        error_count: Number of errors encountered.
    """

    id: str
    name: str
    handler: Callable
    event_types: Set[str] = field(default_factory=set)
    patterns: Set[str] = field(default_factory=set)
    priority: int = 0
    is_async: bool = False
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_executed: Optional[datetime] = None
    execution_count: int = 0
    error_count: int = 0

    def update_execution(self, success: bool) -> None:
        """Update execution statistics."""
        self.last_executed = datetime.now(timezone.utc)
        self.execution_count += 1
        if not success:
            self.error_count += 1


@dataclass
class PluginInfo:
    """
    Information about a registered plugin.

    Attributes:
        id: Unique plugin identifier.
        name: Human-readable plugin name.
        version: Plugin version.
        event_types: Event types the plugin publishes.
        subscriptions: Event types the plugin subscribes to.
        is_active: Whether the plugin is active.
        registered_at: When the plugin was registered.
        last_heartbeat: When the plugin last sent a heartbeat.
        metadata: Additional plugin metadata.
    """

    id: str
    name: str
    version: str = "1.0.0"
    event_types: Set[str] = field(default_factory=set)
    subscriptions: Set[str] = field(default_factory=set)
    is_active: bool = True
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_heartbeat: Optional[datetime] = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HandlerInfo:
    """
    Information about a registered event handler.

    Attributes:
        id: Unique handler identifier.
        name: Human-readable handler name.
        handler: The handler callable.
        event_types: Event types this handler processes.
        priority: Handler priority.
        is_async: Whether the handler is asynchronous.
        created_at: When the handler was registered.
    """

    id: str
    name: str
    handler: Callable
    event_types: Set[str] = field(default_factory=set)
    priority: int = 0
    is_async: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventRegistry:
    """
    Central registry for Event Engine components.

    Tracks plugins, handlers, subscribers, and event types.
    Thread-safe for concurrent access.

    Attributes:
        plugins: Dictionary of registered plugins.
        subscribers: Dictionary of registered subscribers.
        handlers: Dictionary of registered handlers.
        event_types: Set of known event types.
        statistics: Runtime statistics.

    Usage:
        >>> registry = EventRegistry()
        >>> registry.register_plugin("radio-module", "Radio Module", "1.0")
        >>> 
        >>> def my_handler(event):
        ...     print(f"Received: {event}")
        >>> 
        >>> registry.register_handler("handler-1", "My Handler", my_handler, ["radio.transmission"])
    """

    def __init__(self) -> None:
        """Initialize the Event Registry."""
        self._lock = threading.RLock()

        self._plugins: Dict[str, PluginInfo] = {}
        self._subscribers: Dict[str, SubscriberInfo] = {}
        self._handlers: Dict[str, HandlerInfo] = {}
        self._event_types: Set[str] = set()

        self._subscribers_by_type: Dict[str, Set[str]] = defaultdict(set)
        self._handlers_by_type: Dict[str, Set[str]] = defaultdict(set)

        self._statistics = {
            "total_events_published": 0,
            "total_events_dispatched": 0,
            "total_errors": 0,
            "start_time": datetime.now(timezone.utc),
        }

    @property
    def plugins(self) -> Dict[str, PluginInfo]:
        """Get all registered plugins."""
        with self._lock:
            return self._plugins.copy()

    @property
    def subscribers(self) -> Dict[str, SubscriberInfo]:
        """Get all registered subscribers."""
        with self._lock:
            return self._subscribers.copy()

    @property
    def handlers(self) -> Dict[str, HandlerInfo]:
        """Get all registered handlers."""
        with self._lock:
            return self._handlers.copy()

    @property
    def event_types(self) -> Set[str]:
        """Get all known event types."""
        with self._lock:
            return self._event_types.copy()

    @property
    def statistics(self) -> Dict[str, Any]:
        """Get runtime statistics."""
        with self._lock:
            return {
                **self._statistics,
                "plugin_count": len(self._plugins),
                "subscriber_count": len(self._subscribers),
                "handler_count": len(self._handlers),
                "event_type_count": len(self._event_types),
                "active_plugins": sum(1 for p in self._plugins.values() if p.is_active),
                "active_subscribers": sum(1 for s in self._subscribers.values() if s.is_active),
            }

    def register_plugin(
        self,
        plugin_id: str,
        name: str,
        version: str = "1.0.0",
        event_types: Optional[List[str]] = None,
        subscriptions: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PluginInfo:
        """
        Register a plugin with the Event Engine.

        Args:
            plugin_id: Unique plugin identifier.
            name: Human-readable plugin name.
            version: Plugin version string.
            event_types: Event types this plugin publishes.
            subscriptions: Event types this plugin subscribes to.
            metadata: Additional plugin metadata.

        Returns:
            The created PluginInfo.

        Raises:
            ValueError: If plugin_id is already registered.
        """
        with self._lock:
            if plugin_id in self._plugins:
                raise ValueError(f"Plugin {plugin_id} is already registered")

            plugin = PluginInfo(
                id=plugin_id,
                name=name,
                version=version,
                event_types=set(event_types or []),
                subscriptions=set(subscriptions or []),
                metadata=metadata or {},
            )

            self._plugins[plugin_id] = plugin
            self._event_types.update(plugin.event_types)

            for event_type in plugin.subscriptions:
                self._subscribers_by_type[event_type].add(plugin_id)

            return plugin

    def unregister_plugin(self, plugin_id: str) -> bool:
        """
        Unregister a plugin from the Event Engine.

        Args:
            plugin_id: Plugin identifier to unregister.

        Returns:
            True if the plugin was unregistered, False if not found.
        """
        with self._lock:
            if plugin_id not in self._plugins:
                return False

            plugin = self._plugins.pop(plugin_id)

            for event_type in plugin.subscriptions:
                self._subscribers_by_type[event_type].discard(plugin_id)

            return True

    def register_subscriber(
        self,
        subscriber_id: str,
        name: str,
        handler: Callable,
        event_types: Optional[List[str]] = None,
        patterns: Optional[List[str]] = None,
        priority: int = 0,
        is_async: bool = False,
    ) -> SubscriberInfo:
        """
        Register a subscriber for event notifications.

        Args:
            subscriber_id: Unique subscriber identifier.
            name: Human-readable subscriber name.
            handler: Callable that processes events.
            event_types: Specific event types to subscribe to.
            patterns: Wildcard patterns (e.g., "radio.*", "*.error").
            priority: Subscriber priority (higher = earlier execution).
            is_async: Whether the handler is asynchronous.

        Returns:
            The created SubscriberInfo.

        Raises:
            ValueError: If subscriber_id is already registered.
        """
        with self._lock:
            if subscriber_id in self._subscribers:
                raise ValueError(f"Subscriber {subscriber_id} is already registered")

            subscriber = SubscriberInfo(
                id=subscriber_id,
                name=name,
                handler=handler,
                event_types=set(event_types or []),
                patterns=set(patterns or []),
                priority=priority,
                is_async=is_async,
            )

            self._subscribers[subscriber_id] = subscriber

            for event_type in subscriber.event_types:
                self._subscribers_by_type[event_type].add(subscriber_id)
                self._event_types.add(event_type)

            return subscriber

    def unregister_subscriber(self, subscriber_id: str) -> bool:
        """
        Unregister a subscriber.

        Args:
            subscriber_id: Subscriber identifier to unregister.

        Returns:
            True if the subscriber was unregistered, False if not found.
        """
        with self._lock:
            if subscriber_id not in self._subscribers:
                return False

            subscriber = self._subscribers.pop(subscriber_id)

            for event_type in subscriber.event_types:
                self._subscribers_by_type[event_type].discard(subscriber_id)

            return True

    def register_handler(
        self,
        handler_id: str,
        name: str,
        handler: Callable,
        event_types: Optional[List[str]] = None,
        priority: int = 0,
        is_async: bool = False,
    ) -> HandlerInfo:
        """
        Register an event handler.

        Args:
            handler_id: Unique handler identifier.
            name: Human-readable handler name.
            handler: Callable that processes events.
            event_types: Event types this handler processes.
            priority: Handler priority.
            is_async: Whether the handler is asynchronous.

        Returns:
            The created HandlerInfo.

        Raises:
            ValueError: If handler_id is already registered.
        """
        with self._lock:
            if handler_id in self._handlers:
                raise ValueError(f"Handler {handler_id} is already registered")

            handler_info = HandlerInfo(
                id=handler_id,
                name=name,
                handler=handler,
                event_types=set(event_types or []),
                priority=priority,
                is_async=is_async,
            )

            self._handlers[handler_id] = handler_info

            for event_type in handler_info.event_types:
                self._handlers_by_type[event_type].add(handler_id)
                self._event_types.add(event_type)

            return handler_info

    def unregister_handler(self, handler_id: str) -> bool:
        """
        Unregister an event handler.

        Args:
            handler_id: Handler identifier to unregister.

        Returns:
            True if the handler was unregistered, False if not found.
        """
        with self._lock:
            if handler_id not in self._handlers:
                return False

            handler = self._handlers.pop(handler_id)

            for event_type in handler.event_types:
                self._handlers_by_type[event_type].discard(handler_id)

            return True

    def get_subscribers_for_event(self, event_type: str) -> List[SubscriberInfo]:
        """
        Get all subscribers that should receive an event.

        Matches both exact event types and wildcard patterns.

        Args:
            event_type: The event type to match.

        Returns:
            List of SubscriberInfo objects sorted by priority.
        """
        with self._lock:
            subscriber_ids = set()

            if event_type in self._subscribers_by_type:
                subscriber_ids.update(self._subscribers_by_type[event_type])

            for subscriber in self._subscribers.values():
                for pattern in subscriber.patterns:
                    if self._match_pattern(event_type, pattern):
                        subscriber_ids.add(subscriber.id)

            subscribers = [
                self._subscribers[sid] for sid in subscriber_ids
                if sid in self._subscribers and self._subscribers[sid].is_active
            ]

            return sorted(subscribers, key=lambda s: s.priority, reverse=True)

    def get_handlers_for_event(self, event_type: str) -> List[HandlerInfo]:
        """
        Get all handlers that should process an event.

        Args:
            event_type: The event type to match.

        Returns:
            List of HandlerInfo objects sorted by priority.
        """
        with self._lock:
            handler_ids = set()

            if event_type in self._handlers_by_type:
                handler_ids.update(self._handlers_by_type[event_type])

            handlers = [
                self._handlers[hid] for hid in handler_ids
                if hid in self._handlers
            ]

            return sorted(handlers, key=lambda h: h.priority, reverse=True)

    def register_event_type(self, event_type: str) -> None:
        """
        Register a new event type.

        Args:
            event_type: The event type string.
        """
        with self._lock:
            self._event_types.add(event_type)

    def is_plugin_registered(self, plugin_id: str) -> bool:
        """Check if a plugin is registered."""
        with self._lock:
            return plugin_id in self._plugins

    def is_subscriber_registered(self, subscriber_id: str) -> bool:
        """Check if a subscriber is registered."""
        with self._lock:
            return subscriber_id in self._subscribers

    def is_handler_registered(self, handler_id: str) -> bool:
        """Check if a handler is registered."""
        with self._lock:
            return handler_id in self._handlers

    def get_plugin(self, plugin_id: str) -> Optional[PluginInfo]:
        """Get plugin information by ID."""
        with self._lock:
            return self._plugins.get(plugin_id)

    def get_subscriber(self, subscriber_id: str) -> Optional[SubscriberInfo]:
        """Get subscriber information by ID."""
        with self._lock:
            return self._subscribers.get(subscriber_id)

    def get_handler(self, handler_id: str) -> Optional[HandlerInfo]:
        """Get handler information by ID."""
        with self._lock:
            return self._handlers.get(handler_id)

    def update_statistics(self, **kwargs: Any) -> None:
        """
        Update runtime statistics.

        Args:
            **kwargs: Statistics to update.
        """
        with self._lock:
            self._statistics.update(kwargs)

    @staticmethod
    def _match_pattern(event_type: str, pattern: str) -> bool:
        """
        Match an event type against a wildcard pattern.

        Args:
            event_type: The event type to match.
            pattern: Pattern with * wildcards.

        Returns:
            True if the event type matches the pattern.
        """
        if pattern == "*":
            return True

        if pattern.startswith("*."):
            suffix = pattern[2:]
            return event_type.endswith(suffix)

        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return event_type.startswith(prefix)

        return event_type == pattern

    def clear(self) -> None:
        """Clear all registrations. Use with caution."""
        with self._lock:
            self._plugins.clear()
            self._subscribers.clear()
            self._handlers.clear()
            self._event_types.clear()
            self._subscribers_by_type.clear()
            self._handlers_by_type.clear()

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert registry state to dictionary.

        Returns:
            Dictionary representation of the registry.
        """
        with self._lock:
            return {
                "plugins": {
                    pid: {
                        "name": p.name,
                        "version": p.version,
                        "event_types": list(p.event_types),
                        "is_active": p.is_active,
                    }
                    for pid, p in self._plugins.items()
                },
                "subscribers": {
                    sid: {
                        "name": s.name,
                        "event_types": list(s.event_types),
                        "priority": s.priority,
                        "is_active": s.is_active,
                        "execution_count": s.execution_count,
                    }
                    for sid, s in self._subscribers.items()
                },
                "handlers": {
                    hid: {
                        "name": h.name,
                        "event_types": list(h.event_types),
                        "priority": h.priority,
                    }
                    for hid, h in self._handlers.items()
                },
                "event_types": list(self._event_types),
                "statistics": self.statistics,
            }
