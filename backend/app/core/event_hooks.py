"""
Event Hooks Module.

Provides hook system for extending the Event Engine lifecycle.
Hooks allow custom code to execute at specific points in event processing.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import UUID

logger = logging.getLogger(__name__)


HookPhase = str
"""Hook phase identifier."""

HOOK_BEFORE_PUBLISH = "before_publish"
"""Hook called before event is validated and processed."""

HOOK_AFTER_PUBLISH = "after_publish"
"""Hook called after event is successfully published."""

HOOK_BEFORE_STORE = "before_store"
"""Hook called before event is persisted to database."""

HOOK_AFTER_STORE = "after_store"
"""Hook called after event is persisted to database."""

HOOK_BEFORE_DISPATCH = "before_dispatch"
"""Hook called before event is dispatched to subscribers."""

HOOK_AFTER_DISPATCH = "after_dispatch"
"""Hook called after event is dispatched to all subscribers."""

HOOK_BEFORE_NOTIFY_AI = "before_notify_ai"
"""Hook called before AI engine is notified."""

HOOK_AFTER_NOTIFY_AI = "after_notify_ai"
"""Hook called after AI engine is notified."""

HOOK_BEFORE_NOTIFY_PLUGINS = "before_notify_plugins"
"""Hook called before plugins are notified."""

HOOK_AFTER_NOTIFY_PLUGINS = "after_notify_plugins"
"""Hook called after plugins are notified."""

HOOK_BEFORE_BROADCAST = "before_broadcast"
"""Hook called before event is broadcast via WebSocket."""

HOOK_AFTER_BROADCAST = "after_broadcast"
"""Hook called after event is broadcast via WebSocket."""

ALL_HOOK_PHASES = {
    HOOK_BEFORE_PUBLISH,
    HOOK_AFTER_PUBLISH,
    HOOK_BEFORE_STORE,
    HOOK_AFTER_STORE,
    HOOK_BEFORE_DISPATCH,
    HOOK_AFTER_DISPATCH,
    HOOK_BEFORE_NOTIFY_AI,
    HOOK_AFTER_NOTIFY_AI,
    HOOK_BEFORE_NOTIFY_PLUGINS,
    HOOK_AFTER_NOTIFY_PLUGINS,
    HOOK_BEFORE_BROADCAST,
    HOOK_AFTER_BROADCAST,
}


@dataclass
class HookInfo:
    """
    Information about a registered hook.

    Attributes:
        id: Unique hook identifier.
        name: Human-readable hook name.
        phase: The hook phase this hook belongs to.
        handler: The hook handler callable.
        event_types: Event types this hook applies to (None = all).
        priority: Hook execution priority.
        is_async: Whether the hook is asynchronous.
        enabled: Whether the hook is currently enabled.
        created_at: When the hook was registered.
        execution_count: Number of times the hook has executed.
    """

    id: str
    name: str
    phase: HookPhase
    handler: Callable
    event_types: Optional[Set[str]] = None
    priority: int = 0
    is_async: bool = False
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    execution_count: int = 0
    last_executed: Optional[datetime] = None

    def matches_event(self, event_type: str) -> bool:
        """
        Check if this hook matches the given event type.

        Args:
            event_type: The event type to check.

        Returns:
            True if the hook applies to this event type.
        """
        if self.event_types is None:
            return True
        return event_type in self.event_types

    def update_execution(self) -> None:
        """Update execution statistics."""
        self.execution_count += 1
        self.last_executed = datetime.now(timezone.utc)


class EventHooks:
    """
    Hook system for Event Engine lifecycle extension.

    Allows registering handlers that execute at specific points
    during event processing. Supports both sync and async hooks.

    Attributes:
        hooks: Dictionary of hooks by phase.

    Usage:
        >>> hooks = EventHooks()
        >>> 
        >>> def my_before_store_hook(event, context):
        ...     print(f"Before storing: {event.title}")
        ...     return event
        >>> 
        >>> hooks.register(
        ...     hook_id="my-hook",
        ...     name="My Before Store Hook",
        ...     phase=HOOK_BEFORE_STORE,
        ...     handler=my_before_store_hook,
        ... )
    """

    def __init__(self) -> None:
        """Initialize the Event Hooks system."""
        self._hooks: Dict[HookPhase, List[HookInfo]] = defaultdict(list)
        self._hook_count = 0

    def register(
        self,
        hook_id: str,
        name: str,
        phase: HookPhase,
        handler: Callable,
        event_types: Optional[List[str]] = None,
        priority: int = 0,
        is_async: bool = False,
    ) -> HookInfo:
        """
        Register a hook handler.

        Args:
            hook_id: Unique hook identifier.
            name: Human-readable hook name.
            phase: The hook phase to attach to.
            handler: Callable that executes when hook is triggered.
            event_types: Optional list of event types this hook applies to.
            priority: Hook execution priority (higher = earlier).
            is_async: Whether the handler is asynchronous.

        Returns:
            The created HookInfo.

        Raises:
            ValueError: If phase is not valid or hook_id is duplicate.
        """
        if phase not in ALL_HOOK_PHASES:
            raise ValueError(f"Invalid hook phase: {phase}")

        existing = self.get_hook(hook_id)
        if existing is not None:
            raise ValueError(f"Hook {hook_id} is already registered")

        hook = HookInfo(
            id=hook_id,
            name=name,
            phase=phase,
            handler=handler,
            event_types=set(event_types) if event_types else None,
            priority=priority,
            is_async=is_async,
        )

        self._hooks[phase].append(hook)
        self._hooks[phase].sort(key=lambda h: h.priority, reverse=True)
        self._hook_count += 1

        logger.debug(
            f"Registered hook: {hook_id} for phase {phase}",
            extra={"phase": phase, "priority": priority}
        )

        return hook

    def unregister(self, hook_id: str) -> bool:
        """
        Unregister a hook by ID.

        Args:
            hook_id: Hook identifier to unregister.

        Returns:
            True if the hook was unregistered, False if not found.
        """
        for phase, hooks in self._hooks.items():
            for hook in hooks:
                if hook.id == hook_id:
                    hooks.remove(hook)
                    self._hook_count -= 1
                    logger.debug(f"Unregistered hook: {hook_id}")
                    return True
        return False

    def get_hook(self, hook_id: str) -> Optional[HookInfo]:
        """
        Get a hook by ID.

        Args:
            hook_id: Hook identifier.

        Returns:
            HookInfo if found, None otherwise.
        """
        for hooks in self._hooks.values():
            for hook in hooks:
                if hook.id == hook_id:
                    return hook
        return None

    def get_hooks_for_phase(self, phase: HookPhase) -> List[HookInfo]:
        """
        Get all hooks for a specific phase.

        Args:
            phase: The hook phase.

        Returns:
            List of HookInfo sorted by priority.
        """
        return [hook for hook in self._hooks.get(phase, []) if hook.enabled]

    def get_hooks_for_event(
        self,
        phase: HookPhase,
        event_type: str,
    ) -> List[HookInfo]:
        """
        Get applicable hooks for an event at a specific phase.

        Args:
            phase: The hook phase.
            event_type: The event type.

        Returns:
            List of matching hooks sorted by priority.
        """
        hooks = self.get_hooks_for_phase(phase)
        return [hook for hook in hooks if hook.matches_event(event_type)]

    async def trigger(
        self,
        phase: HookPhase,
        event: Any,
        context: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Trigger all hooks for a phase.

        Hooks are executed in priority order. Async hooks are awaited.
        The event is passed through each hook, allowing modifications.

        Args:
            phase: The hook phase to trigger.
            event: The event object being processed.
            context: The EventContext.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.

        Returns:
            The event, potentially modified by hooks.
        """
        hooks = self.get_hooks_for_phase(phase)

        if not hooks:
            return event

        logger.debug(
            f"Triggering {len(hooks)} hooks for phase {phase}",
            extra={"hook_count": len(hooks)}
        )

        for hook in hooks:
            if not hook.matches_event(getattr(event, 'category', str(event)) if hasattr(event, 'category') else str(type(event))):
                continue

            try:
                hook.update_execution()

                if hook.is_async:
                    if asyncio.iscoroutinefunction(hook.handler):
                        result = await hook.handler(event, context, *args, **kwargs)
                    else:
                        result = hook.handler(event, context, *args, **kwargs)
                else:
                    result = hook.handler(event, context, *args, **kwargs)

                if result is not None:
                    event = result

                logger.debug(
                    f"Hook {hook.id} executed successfully",
                    extra={"hook_id": hook.id, "phase": phase}
                )

            except Exception as e:
                logger.error(
                    f"Hook {hook.id} failed: {e}",
                    extra={
                        "hook_id": hook.id,
                        "phase": phase,
                        "error": str(e),
                    }
                )

        return event

    def trigger_sync(
        self,
        phase: HookPhase,
        event: Any,
        context: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Synchronously trigger all hooks for a phase.

        Use this for non-async contexts.

        Args:
            phase: The hook phase to trigger.
            event: The event object being processed.
            context: The EventContext.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.

        Returns:
            The event, potentially modified by hooks.
        """
        hooks = self.get_hooks_for_phase(phase)

        if not hooks:
            return event

        for hook in hooks:
            if not hook.matches_event(getattr(event, 'category', str(event)) if hasattr(event, 'category') else str(type(event))):
                continue

            try:
                hook.update_execution()
                result = hook.handler(event, context, *args, **kwargs)

                if result is not None:
                    event = result

            except Exception as e:
                logger.error(
                    f"Hook {hook.id} failed: {e}",
                    extra={"hook_id": hook.id, "phase": phase}
                )

        return event

    def enable(self, hook_id: str) -> bool:
        """
        Enable a hook.

        Args:
            hook_id: Hook identifier.

        Returns:
            True if the hook was enabled, False if not found.
        """
        hook = self.get_hook(hook_id)
        if hook:
            hook.enabled = True
            return True
        return False

    def disable(self, hook_id: str) -> bool:
        """
        Disable a hook without unregistering it.

        Args:
            hook_id: Hook identifier.

        Returns:
            True if the hook was disabled, False if not found.
        """
        hook = self.get_hook(hook_id)
        if hook:
            hook.enabled = False
            return True
        return False

    def clear(self, phase: Optional[HookPhase] = None) -> int:
        """
        Clear hooks, optionally for a specific phase.

        Args:
            phase: Optional phase to clear. If None, clears all.

        Returns:
            Number of hooks cleared.
        """
        if phase:
            count = len(self._hooks.get(phase, []))
            self._hooks[phase].clear()
        else:
            count = self._hook_count
            self._hooks.clear()
            self._hook_count = 0

        return count

    @property
    def hook_count(self) -> int:
        """Get total number of registered hooks."""
        return self._hook_count

    @property
    def phases(self) -> List[HookPhase]:
        """Get list of phases with registered hooks."""
        return [phase for phase, hooks in self._hooks.items() if hooks]

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get hook execution statistics.

        Returns:
            Dictionary with hook statistics.
        """
        stats = {
            "total_hooks": self._hook_count,
            "phases": {},
        }

        for phase in ALL_HOOK_PHASES:
            hooks = self._hooks.get(phase, [])
            stats["phases"][phase] = {
                "count": len(hooks),
                "enabled": sum(1 for h in hooks if h.enabled),
                "total_executions": sum(h.execution_count for h in hooks),
            }

        return stats

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert hooks state to dictionary.

        Returns:
            Dictionary representation of all hooks.
        """
        result = {}

        for phase, hooks in self._hooks.items():
            result[phase] = [
                {
                    "id": h.id,
                    "name": h.name,
                    "priority": h.priority,
                    "is_async": h.is_async,
                    "enabled": h.enabled,
                    "event_types": list(h.event_types) if h.event_types else None,
                    "execution_count": h.execution_count,
                }
                for h in hooks
            ]

        return result
