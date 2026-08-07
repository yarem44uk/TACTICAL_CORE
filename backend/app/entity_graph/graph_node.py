from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID, uuid4


@dataclass
class GraphNode:
    """Represents an entity node in the Entity Graph."""
    node_id: UUID = field(default_factory=uuid4)
    entity_id: str = ""
    entity_type: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": str(self.node_id),
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "attributes": self.attributes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GraphNode:
        return cls(
            node_id=UUID(data["node_id"]),
            entity_id=data["entity_id"],
            entity_type=data["entity_type"],
            attributes=data.get("attributes", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
