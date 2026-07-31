"""Entity Definitions.

Core entity model for Intelligence Core.

Author: Tactical Core Engineering Team
Version: 2.0 (Constitutional Compliance)

CONSTITUTIONAL COMPLIANCE:
    - Entity follows ENTITY-001 lifecycle model
    - Fresh entity starts at UNKNOWN status
    - confidence is first-class property
    - No physical deletion - lifecycle transitions only
    - Serialization preserves all constitutional fields
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4

from app.intelligence.entity.types import EntityType, EntityStatus, Priority


@dataclass
class EntityData:
    """Entity data payload.

    Flexible data container for entity-specific information.
    The structure depends on the entity type.

    Attributes:
        callsign: Operational callsign.
        name: Entity name.
        description: Human-readable description.
        latitude: GPS latitude coordinate.
        longitude: GPS longitude coordinate.
        altitude: Altitude in meters.
        status_text: Current status description.
        custom_fields: Additional custom fields.
        tags: Entity tags/labels.
    """

    callsign: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    status_text: Optional[str] = None
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation.
        """
        return {
            "callsign": self.callsign,
            "name": self.name,
            "description": self.description,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "status_text": self.status_text,
            "custom_fields": self.custom_fields,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EntityData":
        """Create from dictionary.

        Args:
            data: Dictionary data.

        Returns:
            EntityData instance.
        """
        return cls(
            callsign=data.get("callsign"),
            name=data.get("name"),
            description=data.get("description"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            altitude=data.get("altitude"),
            status_text=data.get("status_text"),
            custom_fields=data.get("custom_fields", {}),
            tags=set(data.get("tags", [])),
        )


@dataclass
class Entity:
    """Base entity model.

    Represents any tracked object in the Intelligence Core.
    Entities are identified by UUID and typed by EntityType.

    Constitutional Properties:
    - id: Unique entity identifier
    - entity_type: Type classification
    - status: Operational lifecycle state
    - data: Entity data payload
    - priority: Entity priority
    - source: Origin source/plugin
    - confidence: Evidence strength measure
    - external_ids: External system IDs
    - created_at: Creation timestamp
    - updated_at: Last update timestamp

    Attributes:
        id: Unique entity identifier.
        entity_type: Type classification.
        status: Current status (per ENTITY-001).
        data: Entity data payload.
        priority: Entity priority.
        source: Origin source/plugin.
        confidence: Confidence in current assessment (0.0-1.0).
        external_ids: External system IDs.
        metadata: Additional metadata.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    id: UUID
    entity_type: EntityType
    status: EntityStatus = EntityStatus.UNKNOWN
    data: EntityData = field(default_factory=EntityData)
    priority: Priority = Priority.MEDIUM
    source: str = ""
    confidence: float = 0.0  # Constitutional first-class property
    external_ids: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def display_name(self) -> str:
        """Get display name.

        Returns:
            Callsign, name, or type with ID.
        """
        if self.data.callsign:
            return self.data.callsign
        if self.data.name:
            return self.data.name
        return f"{self.entity_type.value}:{self.id}"

    @property
    def has_location(self) -> bool:
        """Check if entity has location data.

        Returns:
            True if latitude and longitude are set.
        """
        return (
            self.data.latitude is not None
            and self.data.longitude is not None
        )

    @property
    def location_tuple(self) -> Optional[tuple[float, float]]:
        """Get location as tuple.

        Returns:
            (latitude, longitude) or None.
        """
        if self.has_location:
            return (self.data.latitude, self.data.longitude)
        return None

    def add_tag(self, tag: str) -> None:
        """Add a tag.

        Args:
            tag: Tag to add.
        """
        self.data.tags.add(tag)
        self.mark_updated()

    def remove_tag(self, tag: str) -> None:
        """Remove a tag.

        Args:
            tag: Tag to remove.
        """
        self.data.tags.discard(tag)
        self.mark_updated()

    def add_external_id(self, source: str, external_id: str) -> None:
        """Add an external ID.

        Args:
            source: Source system identifier.
            external_id: External ID value.
        """
        self.external_ids[source] = external_id
        self.mark_updated()

    def get_external_id(self, source: str) -> Optional[str]:
        """Get external ID by source.

        Args:
            source: Source system identifier.

        Returns:
            External ID or None if not found.
        """
        return self.external_ids.get(source)

    def update_confidence(self, new_confidence: float) -> None:
        """Update confidence level.

        Args:
            new_confidence: New confidence value (0.0-1.0).
        """
        if not 0.0 <= new_confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {new_confidence}")
        self.confidence = new_confidence
        self.mark_updated()

    def mark_updated(self) -> None:
        """Mark entity as updated."""
        self.updated_at = datetime.now(timezone.utc)

    def mark_inactive(self) -> None:
        """Mark entity as inactive.

        Constitutional lifecycle transition.
        """
        self.status = EntityStatus.INACTIVE
        self.mark_updated()

    def mark_archived(self) -> None:
        """Mark entity as archived.

        Constitutional lifecycle transition.
        """
        self.status = EntityStatus.ARCHIVED
        self.mark_updated()

    def mark_merged(self, target_id: UUID) -> None:
        """Mark entity as merged into another.

        Constitutional lifecycle transition.

        Args:
            target_id: ID of the entity this was merged into.
        """
        self.status = EntityStatus.MERGED
        self.metadata["merged_into"] = str(target_id)
        self.mark_updated()

    def mark_superseded(self, replacement_id: UUID) -> None:
        """Mark entity as superseded by another.

        Constitutional lifecycle transition.

        Args:
            replacement_id: ID of the replacing entity.
        """
        self.status = EntityStatus.SUPERSEDED
        self.metadata["superseded_by"] = str(replacement_id)
        self.mark_updated()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation.
        """
        return {
            "id": str(self.id),
            "entity_type": self.entity_type.value,
            "status": self.status.value,
            "data": self.data.to_dict() if self.data else None,
            "priority": self.priority.value,
            "source": self.source,
            "confidence": self.confidence,
            "external_ids": self.external_ids,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Entity":
        """Create from dictionary.

        Args:
            data: Dictionary data.

        Returns:
            Entity instance.
        """
        # Parse UUID
        entity_id = data.get("id")
        if isinstance(entity_id, str):
            entity_id = UUID(entity_id)
        elif not isinstance(entity_id, UUID):
            entity_id = uuid4()

        # Parse entity_type
        entity_type_str = data.get("entity_type", "unknown")
        try:
            entity_type = EntityType(entity_type_str)
        except ValueError:
            raise ValueError(f"Invalid entity_type: {entity_type_str}")

        # Parse status
        status_str = data.get("status", "unknown")
        try:
            status = EntityStatus(status_str)
        except ValueError:
            raise ValueError(f"Invalid status: {status_str}")

        # Parse priority
        priority_str = data.get("priority", "medium")
        try:
            priority = Priority(priority_str)
        except ValueError:
            raise ValueError(f"Invalid priority: {priority_str}")

        # Parse data
        data_dict = data.get("data", {})
        entity_data = EntityData.from_dict(data_dict) if data_dict else EntityData()

        # Parse timestamps
        created_at = data.get("created_at")
        if created_at:
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
        else:
            created_at = datetime.now(timezone.utc)

        updated_at = data.get("updated_at")
        if updated_at:
            if isinstance(updated_at, str):
                updated_at = datetime.fromisoformat(updated_at)
        else:
            updated_at = datetime.now(timezone.utc)

        # Parse confidence
        confidence = data.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
            confidence = 0.0

        return cls(
            id=entity_id,
            entity_type=entity_type,
            status=status,
            data=entity_data,
            priority=priority,
            source=data.get("source", ""),
            confidence=confidence,
            external_ids=data.get("external_ids", {}),
            metadata=data.get("metadata", {}),
            created_at=created_at,
            updated_at=updated_at,
        )



    @classmethod
    def create(
        cls,
        entity_type: EntityType,
        source: str = "",
        data: Optional["EntityData"] = None,
        priority: "Priority" = None,
        confidence: float = 0.0,
    ) -> "Entity":
        """Create a new Entity instance.

        This is a factory method for Entity instantiation.
        Identity Resolution must be performed by the caller (EntityManager)
        before this method is called through the canonical flow.

        Args:
            entity_type: Type of entity.
            source: Origin source/plugin.
            data: Initial entity data.
            priority: Entity priority.
            confidence: Initial confidence level.

        Returns:
            New Entity instance.
        """
        from app.intelligence.entity.types import Priority as PriorityType

        entity_id = uuid4()
        status = EntityStatus.UNKNOWN  # Fresh entities start at UNKNOWN

        return cls(
            id=entity_id,
            entity_type=entity_type,
            status=status,
            data=data or EntityData(),
            priority=priority if priority is not None else PriorityType.MEDIUM,
            source=source,
            confidence=confidence,
            external_ids={},
            metadata={},
        )


@dataclass
class ExternalIdentity:
    """External system identity.

    Represents an identity from an external system.

    Attributes:
        id: Unique identifier for this identity record.
        entity_id: ID of the associated entity.
        source: External system identifier.
        external_id: ID in the external system.
        is_verified: Whether identity has been verified.
        verified_at: When identity was verified.
        created_at: When identity was created.
    """

    id: UUID = field(default_factory=uuid4)
    entity_id: UUID = field(default_factory=uuid4)
    source: str = ""
    external_id: str = ""
    is_verified: bool = False
    verified_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def mark_verified(self) -> None:
        """Mark identity as verified."""
        self.is_verified = True
        self.verified_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation.
        """
        return {
            "id": str(self.id),
            "entity_id": str(self.entity_id),
            "source": self.source,
            "external_id": self.external_id,
            "is_verified": self.is_verified,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExternalIdentity":
        """Create from dictionary.

        Args:
            data: Dictionary data.

        Returns:
            ExternalIdentity instance.
        """
        entity_id = data.get("entity_id")
        if isinstance(entity_id, str):
            entity_id = UUID(entity_id)

        verified_at = data.get("verified_at")
        if verified_at and isinstance(verified_at, str):
            verified_at = datetime.fromisoformat(verified_at)

        created_at = data.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return cls(
            id=UUID(data.get("id", uuid4())),
            entity_id=entity_id or uuid4(),
            source=data.get("source", ""),
            external_id=data.get("external_id", ""),
            is_verified=data.get("is_verified", False),
            verified_at=verified_at,
            created_at=created_at,
        )
