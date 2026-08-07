from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4


@dataclass
class GraphEdge:
    """Represents a relationship between two GraphNodes."""
    edge_id: UUID = field(default_factory=uuid4)
    source_node: str = ""  # node_id of source
    target_node: str = ""  # node_id of target
    relation_type: str = ""
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": str(self.edge_id),
            "source_node": self.source_node,
            "target_node": self.target_node,
            "relation_type": self.relation_type,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GraphEdge:
        return cls(
            edge_id=UUID(data["edge_id"]),
            source_node=data["source_node"],
            target_node=data["target_node"],
            relation_type=data["relation_type"],
            confidence=data.get("confidence", 1.0),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
        )
