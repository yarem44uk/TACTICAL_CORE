from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List
from app.event.event import Event


class IEventFilter(ABC):
    """
    Interface for event filtering.
    
    All filters must be immutable and thread-safe.
    Filtering is a pure operation — no side effects.
    """

    @abstractmethod
    def filter(self, events: List[Event]) -> List[Event]:
        """
        Filter events and return matching subset.
        
        Args:
            events: List of events to filter.
            
        Returns:
            List of events that pass the filter.
        """
        pass
