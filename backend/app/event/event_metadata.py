from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class EventMetadata:
    """
    Immutable metadata attached to an event.
    
    Metadata is created at event creation time and cannot be modified.
    Use a new event to record metadata changes.
    """

    tags: list[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None

    def __post_init__(self) -> None:
        # Validate tags
        if not isinstance(self.tags, list):
            raise TypeError(f"tags must be a list, got {type(self.tags).__name__}")
        for tag in self.tags:
            if not isinstance(tag, str):
                raise TypeError(f"Each tag must be a str, got {type(tag).__name__}")

        # Validate properties
        if not isinstance(self.properties, dict):
            raise TypeError(
                f"properties must be a dict, got {type(self.properties).__name__}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tags": list(self.tags),
            "properties": dict(self.properties),
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EventMetadata:
        return cls(
            tags=data.get("tags", []),
            properties=data.get("properties", {}),
            correlation_id=data.get("correlation_id"),
        )
