"""
Event History Module.

Maintains in-memory history of events for replay, search, and statistics.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, Iterator, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class HistoryEntry:
    """
    A single entry in the event history.

    Attributes:
        event_id: UUID of the event.
        event_type: Type/category of the event.
        timestamp: When the event was received.
        event: The event object/data.
        context: The event context at time of receipt.
        result: The processing result.
    """

    event_id: UUID
    event_type: str
    timestamp: datetime
    event: Any
    context: Any
    result: Any


@dataclass
class HistoryStatistics:
    """
    Event History statistics.

    Attributes:
        total_events: Total number of events in history.
        events_by_type: Count of events by type.
        oldest_event: Timestamp of oldest event.
        newest_event: Timestamp of newest event.
        memory_usage_bytes: Estimated memory usage.
    """

    total_events: int = 0
    events_by_type: Dict[str, int] = field(default_factory=dict)
    oldest_event: Optional[datetime] = None
    newest_event: Optional[datetime] = None
    memory_usage_bytes: int = 0


class EventHistory:
    """
    In-memory event history with bounded storage.

    Maintains a rolling buffer of recent events for replay,
    search, and statistics. Thread-safe for concurrent access.

    Attributes:
        max_size: Maximum number of events to store.
        events: The event history buffer.

    Usage:
        >>> history = EventHistory(max_size=10000)
        >>> 
        >>> # Add event to history
        >>> history.add(event_id, "radio.transmission", event, context, result)
        >>> 
        >>> # Get last 10 events
        >>> recent = history.last(10)
        >>> 
        >>> # Search events
        >>> results = history.search(event_type="radio.transmission")
        >>> 
        >>> # Replay events
        >>> for entry in history.replay(since=datetime.now() - timedelta(hours=1)):
        ...     process(entry.event)
    """

    def __init__(
        self,
        max_size: int = 10000,
        auto_cleanup: bool = True,
    ) -> None:
        """
        Initialize the Event History.

        Args:
            max_size: Maximum number of events to store.
            auto_cleanup: Whether to automatically remove old events.
        """
        self._max_size = max_size
        self._auto_cleanup = auto_cleanup

        self._lock = threading.RLock()
        self._events: Deque[HistoryEntry] = deque(maxlen=max_size)
        self._events_by_type: Dict[str, Deque[HistoryEntry]] = {}

        self._statistics = {
            "total_added": 0,
            "total_dropped": 0,
            "total_searched": 0,
        }

        logger.info(
            "Event History initialized",
            extra={"max_size": max_size}
        )

    @property
    def max_size(self) -> int:
        """Get the maximum history size."""
        return self._max_size

    @property
    def current_size(self) -> int:
        """Get the current number of events in history."""
        with self._lock:
            return len(self._events)

    @property
    def is_full(self) -> bool:
        """Check if history is at maximum capacity."""
        with self._lock:
            return len(self._events) >= self._max_size

    def add(
        self,
        event_id: UUID,
        event_type: str,
        event: Any,
        context: Any,
        result: Any,
    ) -> None:
        """
        Add an event to history.

        Args:
            event_id: UUID of the event.
            event_type: Type/category of the event.
            event: The event object/data.
            context: The event context.
            result: The processing result.
        """
        with self._lock:
            entry = HistoryEntry(
                event_id=event_id,
                event_type=event_type,
                timestamp=datetime.now(timezone.utc),
                event=event,
                context=context,
                result=result,
            )

            self._events.append(entry)

            if event_type not in self._events_by_type:
                self._events_by_type[event_type] = deque(maxlen=self._max_size)
            self._events_by_type[event_type].append(entry)

            self._statistics["total_added"] += 1

            if self._auto_cleanup and len(self._events) >= self._max_size:
                self._statistics["total_dropped"] += 1

            logger.debug(
                f"Added event to history: {event_id}",
                extra={
                    "event_id": str(event_id),
                    "event_type": event_type,
                    "history_size": len(self._events),
                }
            )

    def last(self, count: int = 10) -> List[HistoryEntry]:
        """
        Get the last N events from history.

        Args:
            count: Number of events to retrieve.

        Returns:
            List of HistoryEntry objects, newest first.
        """
        with self._lock:
            events = list(self._events)
            events.reverse()
            return events[:count]

    def first(self, count: int = 10) -> List[HistoryEntry]:
        """
        Get the first N events from history.

        Args:
            count: Number of events to retrieve.

        Returns:
            List of HistoryEntry objects, oldest first.
        """
        with self._lock:
            return list(self._events)[:count]

    def get(self, event_id: UUID) -> Optional[HistoryEntry]:
        """
        Get a specific event by ID.

        Args:
            event_id: UUID of the event.

        Returns:
            HistoryEntry if found, None otherwise.
        """
        with self._lock:
            for entry in reversed(self._events):
                if entry.event_id == event_id:
                    return entry
            return None

    def search(
        self,
        event_type: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[HistoryEntry]:
        """
        Search events in history.

        Args:
            event_type: Filter by event type.
            since: Events after this time.
            until: Events before this time.
            limit: Maximum results to return.
            offset: Number of results to skip.

        Returns:
            List of matching HistoryEntry objects.
        """
        with self._lock:
            self._statistics["total_searched"] += 1

            results = []

            if event_type and event_type in self._events_by_type:
                source = self._events_by_type[event_type]
            else:
                source = self._events

            for entry in source:
                if event_type and entry.event_type != event_type:
                    continue

                if since and entry.timestamp < since:
                    continue

                if until and entry.timestamp > until:
                    continue

                results.append(entry)

            results.sort(key=lambda e: e.timestamp, reverse=True)

            return results[offset:offset + limit]

    def replay(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        event_type: Optional[str] = None,
    ) -> Iterator[HistoryEntry]:
        """
        Iterate over events in a time range for replay.

        Args:
            since: Start time for replay.
            until: End time for replay.
            event_type: Optional event type filter.

        Yields:
            HistoryEntry objects in chronological order.
        """
        with self._lock:
            source = self._events_by_type.get(event_type, self._events) if event_type else self._events

            for entry in source:
                if since and entry.timestamp < since:
                    continue
                if until and entry.timestamp > until:
                    continue
                if event_type and entry.event_type != event_type:
                    continue

                yield entry

    def replay_by_ids(
        self,
        event_ids: List[UUID],
    ) -> Iterator[HistoryEntry]:
        """
        Replay specific events by their IDs.

        Args:
            event_ids: List of event UUIDs to replay.

        Yields:
            HistoryEntry objects in the order of event_ids.
        """
        event_id_set = set(str(eid) for eid in event_ids)
        entries_by_id = {str(e.event_id): e for e in self._events}

        for event_id in event_ids:
            entry = entries_by_id.get(str(event_id))
            if entry:
                yield entry

    def get_by_type(
        self,
        event_type: str,
        limit: int = 100,
    ) -> List[HistoryEntry]:
        """
        Get events of a specific type.

        Args:
            event_type: The event type to filter by.
            limit: Maximum results to return.

        Returns:
            List of HistoryEntry objects, newest first.
        """
        with self._lock:
            entries = list(self._events_by_type.get(event_type, []))
            entries.reverse()
            return entries[:limit]

    def get_statistics(self) -> HistoryStatistics:
        """
        Get history statistics.

        Returns:
            HistoryStatistics object with current statistics.
        """
        with self._lock:
            events_by_type: Dict[str, int] = {}

            for event_type, entries in self._events_by_type.items():
                events_by_type[event_type] = len(entries)

            oldest = None
            newest = None

            if self._events:
                entries = list(self._events)
                oldest = entries[0].timestamp
                newest = entries[-1].timestamp

            return HistoryStatistics(
                total_events=len(self._events),
                events_by_type=events_by_type,
                oldest_event=oldest,
                newest_event=newest,
                memory_usage_bytes=self._estimate_memory_usage(),
            )

    def _estimate_memory_usage(self) -> int:
        """
        Estimate memory usage of the history buffer.

        Returns:
            Estimated bytes used.
        """
        import sys
        with self._lock:
            total = 0
            for entry in self._events:
                total += sys.getsizeof(entry)
                total += sys.getsizeof(entry.event)
                total += sys.getsizeof(entry.context)
                total += sys.getsizeof(entry.result)
            return total

    def get_recent_types(self, limit: int = 10) -> List[tuple]:
        """
        Get the most common event types in recent history.

        Args:
            limit: Number of top types to return.

        Returns:
            List of (event_type, count) tuples, sorted by count.
        """
        with self._lock:
            type_counts: Dict[str, int] = {}

            for entry in reversed(self._events):
                type_counts[entry.event_type] = type_counts.get(entry.event_type, 0) + 1

            sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
            return sorted_types[:limit]

    def clear(self) -> None:
        """
        Clear all event history.

        Use with caution - this removes all stored events.
        """
        with self._lock:
            self._events.clear()
            self._events_by_type.clear()

            logger.warning("Event history cleared")

    def clear_type(self, event_type: str) -> int:
        """
        Clear events of a specific type.

        Args:
            event_type: The event type to clear.

        Returns:
            Number of events removed.
        """
        with self._lock:
            if event_type not in self._events_by_type:
                return 0

            count = len(self._events_by_type[event_type])
            self._events_by_type[event_type].clear()

            self._events = deque(
                (e for e in self._events if e.event_type != event_type),
                maxlen=self._max_size
            )

            logger.info(
                f"Cleared {count} events of type: {event_type}",
                extra={"event_type": event_type, "count": count}
            )

            return count

    def prune_old(self, before: datetime) -> int:
        """
        Remove events older than a specified time.

        Args:
            before: Remove events before this time.

        Returns:
            Number of events removed.
        """
        with self._lock:
            count = 0

            self._events = deque(
                (e for e in self._events if e.timestamp >= before),
                maxlen=self._max_size
            )

            for event_type in list(self._events_by_type.keys()):
                self._events_by_type[event_type] = deque(
                    (e for e in self._events_by_type[event_type] if e.timestamp >= before),
                    maxlen=self._max_size
                )

                if not self._events_by_type[event_type]:
                    del self._events_by_type[event_type]

                count += 1

            logger.info(
                f"Pruned events before: {before}",
                extra={"before": before.isoformat()}
            )

            return count

    def get_time_range(self) -> tuple:
        """
        Get the time range of events in history.

        Returns:
            Tuple of (oldest, newest) datetime or (None, None) if empty.
        """
        with self._lock:
            if not self._events:
                return (None, None)

            entries = list(self._events)
            return (entries[0].timestamp, entries[-1].timestamp)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert history state to dictionary.

        Returns:
            Dictionary representation of the history.
        """
        with self._lock:
            stats = self.get_statistics()

            return {
                "max_size": self._max_size,
                "current_size": len(self._events),
                "statistics": {
                    "total_added": self._statistics["total_added"],
                    "total_dropped": self._statistics["total_dropped"],
                    "total_searched": self._statistics["total_searched"],
                },
                "event_types": {
                    "count": len(self._events_by_type),
                    "types": list(self._events_by_type.keys()),
                },
                "time_range": {
                    "oldest": stats.oldest_event.isoformat() if stats.oldest_event else None,
                    "newest": stats.newest_event.isoformat() if stats.newest_event else None,
                },
            }
