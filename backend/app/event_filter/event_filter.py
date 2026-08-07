from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, List, Optional, Union

from app.event.event import Event
from app.event.event_metadata import EventMetadata
from app.event.event_types import EventType
from app.event_filter.interfaces.i_event_filter import IEventFilter


class EventTypeFilter(IEventFilter):
    """Filter events by EventType."""

    def __init__(self, event_types: List[EventType]) -> None:
        if not event_types:
            raise ValueError("event_types cannot be empty")
        self._event_types = frozenset(event_types)

    def filter(self, events: List[Event]) -> List[Event]:
        return [e for e in events if e.event_type in self._event_types]


class SourceFilter(IEventFilter):
    """Filter events by source."""

    def __init__(self, sources: List[str]) -> None:
        if not sources:
            raise ValueError("sources cannot be empty")
        self._sources = frozenset(sources)

    def filter(self, events: List[Event]) -> List[Event]:
        return [e for e in events if e.source in self._sources]


class CorrelationIdFilter(IEventFilter):
    """Filter events by correlation_id."""

    def __init__(self, correlation_id: str) -> None:
        if not correlation_id:
            raise ValueError("correlation_id cannot be empty")
        self._correlation_id = correlation_id

    def filter(self, events: List[Event]) -> List[Event]:
        return [
            e for e in events
            if e.metadata and e.metadata.correlation_id == self._correlation_id
        ]


class TimestampRangeFilter(IEventFilter):
    """Filter events by timestamp range."""

    def __init__(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> None:
        if start and end and start > end:
            raise ValueError("start must be before end")
        self._start = start
        self._end = end

    def filter(self, events: List[Event]) -> List[Event]:
        result = events
        if self._start:
            result = [e for e in result if e.timestamp >= self._start]
        if self._end:
            result = [e for e in result if e.timestamp <= self._end]
        return result


class MetadataFilter(IEventFilter):
    """Filter events by metadata properties."""

    def __init__(self, property_key: str, property_value: Any) -> None:
        if not property_key:
            raise ValueError("property_key cannot be empty")
        self._key = property_key
        self._value = property_value

    def filter(self, events: List[Event]) -> List[Event]:
        return [
            e for e in events
            if e.metadata
            and e.metadata.properties.get(self._key) == self._value
        ]


class PredicateFilter(IEventFilter):
    """Filter events by arbitrary predicate function."""

    def __init__(self, predicate: Callable[[Event], bool]) -> None:
        if not callable(predicate):
            raise TypeError("predicate must be callable")
        self._predicate = predicate

    def filter(self, events: List[Event]) -> List[Event]:
        return [e for e in events if self._predicate(e)]


class AndFilter(IEventFilter):
    """Logical AND of multiple filters."""

    def __init__(self, *filters: IEventFilter) -> None:
        if not filters:
            raise ValueError("filters cannot be empty")
        self._filters = filters

    def filter(self, events: List[Event]) -> List[Event]:
        result = events
        for f in self._filters:
            result = f.filter(result)
        return result


class OrFilter(IEventFilter):
    """Logical OR of multiple filters."""

    def __init__(self, *filters: IEventFilter) -> None:
        if not filters:
            raise ValueError("filters cannot be empty")
        self._filters = filters

    def filter(self, events: List[Event]) -> List[Event]:
        seen = set()
        result = []
        for f in self._filters:
            for e in f.filter(events):
                if e.event_id not in seen:
                    seen.add(e.event_id)
                    result.append(e)
        return result


class NotFilter(IEventFilter):
    """Logical NOT — events that do NOT match the filter."""

    def __init__(self, inner: IEventFilter) -> None:
        self._inner = inner

    def filter(self, events: List[Event]) -> List[Event]:
        included = {e.event_id for e in self._inner.filter(events)}
        return [e for e in events if e.event_id not in included]
