"""Tests for Identity resolution and mapping.

Verifies identity creation, resolution, mapping management,
and identity merging behavior.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import pytest
from uuid import uuid4

from app.intelligence.entity.identity import (
    IdentityResolver,
    IdentityMapping,
)
from app.intelligence.entity.entity import ExternalIdentity
from app.intelligence.entity.types import EntityType


# =============================================================================
# EXTERNAL IDENTITY TESTS
# =============================================================================

class TestExternalIdentity:
    """Tests for ExternalIdentity class."""

    def test_create_external_identity(self):
        """Test creating an ExternalIdentity with required fields."""
        external_id = "TAK-12345"
        source = "tak-server"

        identity = ExternalIdentity(
            external_id=external_id,
            source=source,
        )

        assert identity.external_id == external_id
        assert identity.source == source
        assert identity.is_verified is False
        assert identity.verified_at is None

    def test_external_identity_with_verified(self):
        """Test ExternalIdentity with verified flag."""
        identity = ExternalIdentity(
            external_id="SIG-001",
            source="signal",
            is_verified=True,
        )

        assert identity.is_verified is True
        assert identity.verified_at is not None

    def test_mark_verified(self):
        """Test marking identity as verified."""
        identity = ExternalIdentity(
            external_id="MQTT-001",
            source="mqtt",
        )

        identity.mark_verified()

        assert identity.is_verified is True
        assert identity.verified_at is not None

    def test_external_identity_to_dict(self):
        """Test ExternalIdentity serialization."""
        identity = ExternalIdentity(
            external_id="ATAK-001",
            source="atak",
        )

        identity_dict = identity.to_dict()

        assert identity_dict["external_id"] == "ATAK-001"
        assert identity_dict["source"] == "atak"
        assert identity_dict["is_verified"] is False


# =============================================================================
# IDENTITY MAPPING TESTS
# =============================================================================

class TestIdentityMapping:
    """Tests for IdentityMapping class."""

    def test_create_identity_mapping(self):
        """Test creating an IdentityMapping."""
        entity_id = uuid4()
        mapping = IdentityMapping(entity_id=entity_id)

        assert mapping.entity_id == entity_id
        assert len(mapping.mappings) == 0

    def test_add_mapping(self):
        """Test adding an external ID mapping."""
        entity_id = uuid4()
        mapping = IdentityMapping(entity_id=entity_id)

        mapping.add_mapping(source="tak", external_id="TAK-123")

        assert len(mapping.mappings) == 1
        assert "TAK-123" in mapping.mappings.get("tak", [])

    def test_add_multiple_mappings_same_source(self):
        """Test adding multiple IDs from same source."""
        entity_id = uuid4()
        mapping = IdentityMapping(entity_id=entity_id)

        mapping.add_mapping(source="tak", external_id="TAK-001")
        mapping.add_mapping(source="tak", external_id="TAK-002")

        assert len(mapping.mappings["tak"]) == 2
        assert "TAK-001" in mapping.mappings["tak"]
        assert "TAK-002" in mapping.mappings["tak"]

    def test_get_external_id(self):
        """Test retrieving external ID by source."""
        entity_id = uuid4()
        mapping = IdentityMapping(entity_id=entity_id)
        mapping.add_mapping(source="signal", external_id="SIG-001")

        ext_id = mapping.get_external_id(source="signal")

        assert ext_id == "SIG-001"

    def test_get_external_id_not_found(self):
        """Test retrieving non-existent external ID."""
        entity_id = uuid4()
        mapping = IdentityMapping(entity_id=entity_id)

        ext_id = mapping.get_external_id(source="nonexistent")

        assert ext_id is None

    def test_get_sources(self):
        """Test getting all sources for an entity."""
        entity_id = uuid4()
        mapping = IdentityMapping(entity_id=entity_id)
        mapping.add_mapping(source="tak", external_id="TAK-001")
        mapping.add_mapping(source="signal", external_id="SIG-001")

        sources = mapping.get_sources()

        assert "tak" in sources
        assert "signal" in sources
        assert len(sources) == 2


# =============================================================================
# IDENTITY RESOLVER TESTS
# =============================================================================

class TestIdentityResolver:
    """Tests for IdentityResolver class."""

    def test_create_identity_resolver(self):
        """Test creating an IdentityResolver."""
        resolver = IdentityResolver()

        assert resolver is not None

    def test_create_identity(self):
        """Test creating a new identity for an entity."""
        entity_id = uuid4()
        resolver = IdentityResolver()

        mapping = resolver.create_identity(
            entity_id=entity_id,
            source="telegram",
            external_id="TG-12345",
        )

        assert mapping is not None
        assert mapping.entity_id == entity_id
        assert "telegram" in mapping.get_sources()

    def test_resolve_by_external_id(self):
        """Test resolving identity by source and external ID."""
        entity_id = uuid4()
        resolver = IdentityResolver()
        resolver.create_identity(
            entity_id=entity_id,
            source="mqtt",
            external_id="MQTT-001",
        )

        resolved_id = resolver.resolve(source="mqtt", external_id="MQTT-001")

        assert resolved_id == entity_id

    def test_resolve_not_found(self):
        """Test resolving non-existent identity."""
        resolver = IdentityResolver()

        result = resolver.resolve(source="nonexistent", external_id="none")

        assert result is None

    def test_get_mapping(self):
        """Test getting identity mapping by entity ID."""
        entity_id = uuid4()
        resolver = IdentityResolver()
        original = resolver.create_identity(
            entity_id=entity_id,
            source="atak",
            external_id="ATAK-MAP-001",
        )

        mapping = resolver.get_mapping(entity_id=entity_id)

        assert mapping is not None
        assert mapping.entity_id == entity_id

    def test_get_mapping_not_found(self):
        """Test getting mapping for non-existent entity."""
        resolver = IdentityResolver()

        mapping = resolver.get_mapping(entity_id=uuid4())

        assert mapping is None

    def test_merge_identities(self):
        """Test merging two entity identities."""
        entity_id_1 = uuid4()
        entity_id_2 = uuid4()
        resolver = IdentityResolver()

        # Create identities for two entities
        resolver.create_identity(
            entity_id=entity_id_1,
            source="signal",
            external_id="SIG-001",
        )
        resolver.create_identity(
            entity_id=entity_id_2,
            source="telegram",
            external_id="TG-001",
        )

        # Merge entity_id_2 into entity_id_1
        merged = resolver.merge(entity_id_2, entity_id_1)

        assert merged is not None
        assert merged.entity_id == entity_id_1
        # Check that TG-001 is now mapped to entity_id_1
        ext_id = merged.get_external_id(source="telegram")
        assert ext_id == "TG-001"

    def test_get_stats(self):
        """Test getting identity resolution statistics."""
        resolver = IdentityResolver()

        # Create some identities
        resolver.create_identity(uuid4(), "s1", "e1")
        resolver.create_identity(uuid4(), "s2", "e2")

        stats = resolver.get_stats()

        assert "total_entities" in stats
        assert "total_external_ids" in stats
        assert stats["total_entities"] >= 2


class TestIdentityResolverEdgeCases:
    """Tests for IdentityResolver edge cases."""

    def test_resolve_with_no_identities(self):
        """Test resolving with empty resolver."""
        resolver = IdentityResolver()

        result = resolver.resolve(source="nonexistent", external_id="none")

        assert result is None

    def test_duplicate_external_id(self):
        """Test handling of duplicate external IDs."""
        resolver = IdentityResolver()
        entity_id = uuid4()

        # First identity
        resolver.create_identity(
            entity_id=entity_id,
            source="test",
            external_id="DUP-001",
        )

        # Try to add duplicate - should update existing
        mapping = resolver.create_identity(
            entity_id=entity_id,
            source="test",
            external_id="DUP-001",
        )

        # Should still only have one ID for this source
        ext_ids = mapping.get_external_id(source="test")
        assert ext_ids == "DUP-001"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
