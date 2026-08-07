from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.event.event import Event


class IEvent(ABC):
    """
    Contract for Event domain objects.
    
    Ensures all event implementations support:
    - Immutable identity
    - Serialization (to_dict / from_dict)
    - Lock-based read access
    """

    @property
    @abstractmethod
    def event_id(self) -> str:
        pass

    @property
    @abstractmethod
    def entity_id(self) -> Optional[str]:
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IEvent":
        pass

    @abstractmethod
    def equals(self, other: "IEvent") -> bool:
        pass

    @abstractmethod
    def get_lock(self) -> Any:
        pass
