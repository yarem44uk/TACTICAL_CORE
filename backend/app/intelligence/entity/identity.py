"""Identity Resolution Module.

Manages entity identity and external ID mapping.

Author: Tactical Core Engineering Team
Version: 2.0 (Constitutional Compliance)

CONSTITUTIONAL COMPLIANCE:
    - Identity Resolution precedes Entity creation (ENTITY-001 Section 11)
    - External identities are first-class properties
    - Match levels: MATCH, PARTIAL_MATCH, NO_MATCH
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4

from app.intelligence.entity.types import IdentityMatchLevel


@dataclass
class IdentityMapping:
    """Maps external IDs to internal entity IDs.

    Attributes:
        entity_id: Internal entity UUID.
        mappings: Dict of source -> list of external IDs.
    """

    entity_id: UUID
    mappings: Dict[str, List[str]] = field(default_factory=dict)

    def add_mapping(self, source: str, external_id: str) -> None:
        """Add an external ID mapping.

        Args:
            source: Source system identifier.
            external_id: External ID value.
        """
        if source not in self.mappings:
            self.mappings[source] = []
        if external_id not in self.mappings[source]:
            self.mappings[source].append(external_id)

    def get_external_id(self, source: str) -> Optional[str]:
        """Get first external ID for a source.

        Args:
            source: Source system identifier.

        Returns:
            External ID or None if not found.
        """
        ids = self.mappings.get(source, [])
        return ids[0] if ids else None

    def get_all_external_ids(self, source: str) -> List[str]:
        """Get all external IDs for a source.

        Args:
            source: Source system identifier.

        Returns:
            List of external IDs.
        """
        return self.mappings.get(source, [])

    def get_sources(self) -> List[str]:
        """Get all sources with mappings.

        Returns:
            List of source identifiers.
        """
        return list(self.mappings.keys())


class IdentityResolver:
    """Resolves external IDs to internal entity IDs.

    Implements Identity Resolution per ENTITY-001 Section 11.

    This resolver maintains the mapping between external identities
    and internal entity IDs, enabling Identity Resolution to
    determine whether an Observation belongs to an existing
    Entity or requires a new Entity.
    """

    def __init__(self) -> None:
        """Initialize IdentityResolver."""
        # entity_id -> IdentityMapping
        self._by_entity: Dict[UUID, IdentityMapping] = {}
        # (source, external_id) -> entity_id
        self._by_external: Dict[tuple[str, str], UUID] = {}

    def create_identity(
        self,
        entity_id: UUID,
        source: str,
        external_id: str,
    ) -> IdentityMapping:
        """Create a new identity mapping.

        Args:
            entity_id: Internal entity UUID.
            source: Source system identifier.
            external_id: External ID value.

        Returns:
            Updated IdentityMapping for the entity.
        """
        # Get or create mapping
        if entity_id not in self._by_entity:
            self._by_entity[entity_id] = IdentityMapping(entity_id=entity_id)

        mapping = self._by_entity[entity_id]
        mapping.add_mapping(source, external_id)

        # Index by external ID
        self._by_external[(source, external_id)] = entity_id

        return mapping

    def resolve(
        self,
        source: str,
        external_id: str,
    ) -> Optional[UUID]:
        """Resolve external ID to entity ID.

        Args:
            source: Source system identifier.
            external_id: External ID value.

        Returns:
            Entity UUID if found, None otherwise.
        """
        return self._by_external.get((source, external_id))

    def resolve_match_level(
        self,
        source: str,
        external_id: str,
    ) -> IdentityMatchLevel:
        """Resolve with match level.

        Args:
            source: Source system identifier.
            external_id: External ID value.

        Returns:
            Match level (MATCH, PARTIAL_MATCH, or NO_MATCH).
        """
        existing_id = self.resolve(source, external_id)
        if existing_id:
            return IdentityMatchLevel.MATCH
        return IdentityMatchLevel.NO_MATCH

    def get_mapping(self, entity_id: UUID) -> Optional[IdentityMapping]:
        """Get identity mapping for an entity.

        Args:
            entity_id: Internal entity UUID.

        Returns:
            IdentityMapping or None if not found.
        """
        return self._by_entity.get(entity_id)

    def merge(
        self,
        source_id: UUID,
        target_id: UUID,
    ) -> IdentityMapping:
        """Merge identities, moving all mappings to target.

        Args:
            source_id: Entity ID to merge from.
            target_id: Entity ID to merge into.

        Returns:
            Updated IdentityMapping for target.
        """
        source_mapping = self._by_entity.get(source_id)
        if not source_mapping:
            return self._by_entity.get(target_id)

        target_mapping = self._by_entity.get(target_id)
        if not target_mapping:
            target_mapping = IdentityMapping(entity_id=target_id)
            self._by_entity[target_id] = target_mapping

        # Move all mappings
        for source, ids in source_mapping.mappings.items():
            for external_id in ids:
                target_mapping.add_mapping(source, external_id)
                self._by_external[(source, external_id)] = target_id

        # Remove source
        del self._by_entity[source_id]

        return target_mapping

    def get_stats(self) -> Dict[str, Any]:
        """Get identity resolution statistics.

        Returns:
            Statistics dictionary.
        """
        total_entities = len(self._by_entity)
        total_external_ids = len(self._by_external)

        sources = set()
        for source, _ in self._by_external.keys():
            sources.add(source)

        return {
            "total_entities": total_entities,
            "total_external_ids": total_external_ids,
            "sources": list(sources),
            "entities_with_multiple_ids": sum(
                1 for m in self._by_entity.values()
                if sum(len(ids) for ids in m.mappings.values()) > 1
            ),
        }

    def clear(self) -> None:
        """Clear all identity mappings."""
        self._by_entity.clear()
        self._by_external.clear()
