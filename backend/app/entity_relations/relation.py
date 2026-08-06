from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID, uuid4


@dataclass
class Relation:
    """Entity relationship domain model."""

    relation_id: str = field(default_factory=lambda: str(uuid4()))
    source_entity_id: str | UUID = ""
    target_entity_id: str | UUID = ""
    relation_type: str = ""
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1
