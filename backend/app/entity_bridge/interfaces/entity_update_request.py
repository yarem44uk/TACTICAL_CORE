"""
EntityUpdateRequest.

Data carrier between EntityBridge and IEntityManager.
Encapsulates everything the bridge needs to tell the manager
about a single entity change derived from one event.

Author: Tactical Core Engineering Team
Version: 1.0
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4


@dataclass
class EntityUpdateRequest:
    """
    Structured request to update (or create) an entity.

    Created by EntityBridge from raw event data and passed to
    IEntityManager.apply_update().

    Attributes:
        request_id: Unique identifier for this update request.
        entity_type: Domain type (e.g. ``"person"``, ``"location"``).
        entity_id: Stable identifier of the target entity.
        updates: Key-value pairs to merge into the entity.
        source_event_id: Correlation back to the originating event.
        correlation_id: Optional trace correlation ID.
        metadata: Extra context the bridge wants to preserve.
        created_at: When this request was instantiated.
    """

    entity_type: str
    entity_id: str | UUID
    updates: Dict[str, Any]
    source_event_id: str | UUID | None = None
    correlation_id: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    request_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_entity_manager_params(self) -> Dict[str, Any]:
        """
        Flatten this request into keyword args for IEntityManager.apply_update().

        Returns:
            Dict ready for ``**kwargs`` expansion.
        """
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "updates": self.updates,
            "source_event_id": self.source_event_id,
        }
