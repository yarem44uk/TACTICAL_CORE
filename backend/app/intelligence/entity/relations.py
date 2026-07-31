"""Entity Relations Module.

Manages relationships between entities.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4

from app.intelligence.entity.types import EntityRelationType


@dataclass
class Relation:
    """Represents a relationship between two entities.

    Attributes:
        id: Unique relation identifier.
        source_id: Source entity UUID.
        target_id: Target entity UUID.
        relation_type: Type of relationship.
        metadata: Additional relation metadata.
        created_at: When relation was created.
        created_by: Who/what created the relation.
    """

    id: UUID
    source_id: UUID
    target_id: UUID
    relation_type: EntityRelationType
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation.
        """
        return {
            "id": str(self.id),
            "source_id": str(self.source_id),
            "target_id": str(self.target_id),
            "relation_type": self.relation_type.value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
        }


class EntityRelations:
    """Manages entity relationships.

    Provides methods to create, query, and manage
    relationships between entities.

    Attributes:
        _relations: All entity relations.
    """

    def __init__(self) -> None:
        """Initialize EntityRelations."""
        self._relations: Dict[UUID, List[Relation]] = {}
        self._by_type: Dict[EntityRelationType, List[Relation]] = {}

    def relate(
        self,
        source_id: UUID,
        target_id: UUID,
        relation_type: EntityRelationType,
        metadata: Optional[Dict[str, Any]] = None,
        created_by: str = "",
    ) -> Relation:
        """Create a relationship between entities.

        Args:
            source_id: Source entity UUID.
            target_id: Target entity UUID.
            relation_type: Type of relationship.
            metadata: Additional metadata.
            created_by: Creator identifier.

        Returns:
            Created Relation.
        """
        relation = Relation(
            id=uuid4(),
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            metadata=metadata or {},
            created_by=created_by,
        )

        # Index by source
        if source_id not in self._relations:
            self._relations[source_id] = []
        self._relations[source_id].append(relation)

        # Index by type
        if relation_type not in self._by_type:
            self._by_type[relation_type] = []
        self._by_type[relation_type].append(relation)

        return relation

    def unrelate(self, relation_id: UUID) -> bool:
        """Remove a relationship.

        Args:
            relation_id: Relation identifier.

        Returns:
            True if removed, False if not found.
        """
        for source_id, relations in self._relations.items():
            for i, rel in enumerate(relations):
                if rel.id == relation_id:
                    relations.pop(i)
                    self._by_type[rel.relation_type].remove(rel)
                    return True
        return False

    def get_relations(
        self,
        entity_id: UUID,
        relation_type: Optional[EntityRelationType] = None,
    ) -> List[Relation]:
        """Get relations for an entity.

        Args:
            entity_id: Entity UUID.
            relation_type: Filter by type.

        Returns:
            List of relations.
        """
        relations = self._relations.get(entity_id, [])

        if relation_type:
            relations = [r for r in relations if r.relation_type == relation_type]

        return relations

    def get_related(
        self,
        entity_id: UUID,
        relation_type: Optional[EntityRelationType] = None,
    ) -> List[UUID]:
        """Get entity IDs related to an entity.

        Args:
            entity_id: Entity UUID.
            relation_type: Filter by type.

        Returns:
            List of related entity UUIDs.
        """
        relations = self.get_relations(entity_id, relation_type)
        return [r.target_id for r in relations]

    def get_by_type(
        self,
        relation_type: EntityRelationType,
    ) -> List[Relation]:
        """Get all relations of a type.

        Args:
            relation_type: Relation type.

        Returns:
            List of relations.
        """
        return self._by_type.get(relation_type, []).copy()

    def get_stats(self) -> Dict[str, Any]:
        """Get relation statistics.

        Returns:
            Dictionary with statistics.
        """
        return {
            "total_relations": sum(len(r) for r in self._relations.values()),
            "entities_with_relations": len(self._relations),
            "by_type": {
                rt.value: len(rels) for rt, rels in self._by_type.items()
            },
        }

    def remove(self, relation_id: UUID) -> bool:
        """Remove a relation by ID.

        Args:
            relation_id: Relation identifier.

        Returns:
            True if removed, False if not found.
        """
        return self.unrelate(relation_id)

    def remove_all(self, source_id: UUID) -> int:
        """Remove all relations for a source entity.

        Args:
            source_id: Source entity UUID.

        Returns:
            Number of relations removed.
        """
        count = 0
        if source_id in self._relations:
            relations = self._relations[source_id]
            for rel in relations:
                # Remove from type index
                if rel.relation_type in self._by_type:
                    self._by_type[rel.relation_type] = [
                        r for r in self._by_type[rel.relation_type]
                        if r.id != rel.id
                    ]
                count += 1
            del self._relations[source_id]
        return count

    def get_relations_by_type(
        self,
        relation_type: EntityRelationType,
    ) -> List["Relation"]:
        """Get all relations of a specific type.

        Args:
            relation_type: Type of relation.

        Returns:
            List of relations.
        """
        return self._by_type.get(relation_type, [])

    def get_related(
        self,
        entity_id: UUID,
        relation_type: Optional[EntityRelationType] = None,
    ) -> List[UUID]:
        """Get all entities related to the given entity.

        Args:
            entity_id: Entity UUID.
            relation_type: Optional filter by relation type.

        Returns:
            List of related entity UUIDs.
        """
        if entity_id not in self._relations:
            return []

        related = []
        for rel in self._relations[entity_id]:
            if relation_type is None or rel.relation_type == relation_type:
                related.append(rel.target_id)

        return related
