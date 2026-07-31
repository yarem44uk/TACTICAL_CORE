"""Tests for Entity and EntityData models.

Verifies entity creation, required fields, UID handling, 
entity type, equality, serialization, and invalid data handling.

Author: Tactical Core Engineering Team
Version: 1.0

"""

import pytest
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID, uuid4

from app.intelligence.entity.entity import Entity, EntityData
from app.intelligence.entity.types import EntityType, EntityStatus, Priority


def create_entity(entity_type: EntityType, **kwargs) -> Entity:
    """Helper to create entity for testing."""
    defaults = {
        'id': uuid4(),
        'entity_type': entity_type,
        'status': EntityStatus.UNKNOWN,
        'data': kwargs.get('data'),
        'priority': kwargs.get('priority', Priority.MEDIUM),
        'source': kwargs.get('source', ''),
    }
    # Remove None values
    defaults = {k: v for k, v in defaults.items() if v is not None}
    return Entity(**defaults)


# =============================================================================
# ENTITY TESTS
# =============================================================================

class TestEntityCreation:
    """Tests for Entity creation with valid data."""

    def test_create_entity_with_required_fields_only(self):
        """Test entity creation with only required fields."""
        entity = Entity(
            id=uuid4(),
            entity_type=EntityType.UNIT,
            status=EntityStatus.UNKNOWN,
        )

        assert entity.id is not None
        assert isinstance(entity.id, UUID)
        assert entity.entity_type == EntityType.UNIT
        assert entity.status == EntityStatus.UNKNOWN

    def test_create_entity_with_all_fields(self):
        """Test entity creation with all optional fields."""
        entity_id = uuid4()
        data = EntityData(callsign="ALPHA-1", name="Alpha Team")

        entity = Entity(
            id=entity_id,
            entity_type=EntityType.VEHICLE,
            status=EntityStatus.UNKNOWN,
            data=data,
            source="tactical-core",
            priority=Priority.HIGH,
        )

        assert entity.id is not None
        assert entity.id == entity_id
        assert entity.entity_type == EntityType.VEHICLE
        assert entity.source == "tactical-core"
        assert entity.data is not None
        assert entity.data.callsign == "ALPHA-1"
        assert entity.priority == Priority.HIGH
        assert entity.status == EntityStatus.UNKNOWN

    def test_entity_has_timestamps(self):
        """Test that entity has created_at and updated_at timestamps."""
        before = datetime.now(timezone.utc)
        entity = Entity(
            id=uuid4(),
            entity_type=EntityType.CONTACT,
            status=EntityStatus.UNKNOWN,
        )
        after = datetime.now(timezone.utc)

        assert entity.created_at is not None
        assert entity.updated_at is not None
        assert before <= entity.created_at <= after
        assert before <= entity.updated_at <= after


class TestEntityUidHandling:
    """Tests for Entity UID handling."""

    def test_entity_id_is_uuid(self):
        """Test that entity ID is a valid UUID."""
        entity = Entity(
            id=uuid4(),
            entity_type=EntityType.ASSET,
            status=EntityStatus.UNKNOWN,
        )

        assert isinstance(entity.id, UUID)
        assert len(str(entity.id)) == 36
        assert "-" in str(entity.id)

    def test_entity_id_is_unique(self):
        """Test that each entity gets a unique ID."""
        entity1 = Entity(id=uuid4(), entity_type=EntityType.UNIT, status=EntityStatus.UNKNOWN)
        entity2 = Entity(id=uuid4(), entity_type=EntityType.UNIT, status=EntityStatus.UNKNOWN)

        assert entity1.id != entity2.id

    def test_entity_id_from_dict(self):
        """Test entity creation from dictionary with specific ID."""
        entity_id = uuid4()
        entity_dict = {
            "id": entity_id,
            "entity_type": EntityType.INCIDENT,
            "status": EntityStatus.ACTIVE,
            "data": {},
            "source": "test",
            "priority": Priority.MEDIUM.value,
        }

        entity = Entity.from_dict(entity_dict)

        assert entity.id == entity_id
        assert entity.entity_type == EntityType.INCIDENT


class TestEntityTypeHandling:
    """Tests for Entity type handling."""

    def test_entity_type_is_entity_type_enum(self):
        """Test that entity_type accepts EntityType enum."""
        entity = Entity(id=uuid4(), entity_type=EntityType.LOCATION, status=EntityStatus.UNKNOWN)

        assert entity.entity_type == EntityType.LOCATION
        assert isinstance(entity.entity_type, EntityType)

    def test_all_entity_types_are_valid(self):
        """Test that all defined EntityType values work."""
        for entity_type in EntityType:
            entity = Entity(id=uuid4(), entity_type=entity_type, status=EntityStatus.UNKNOWN)
            assert entity.entity_type == entity_type

    def test_entity_type_from_string(self):
        """Test creating entity from dict with string type."""
        entity_dict = {
            "id": uuid4(),
            "entity_type": "vehicle",
            "status": EntityStatus.ACTIVE,
            "data": {},
            "source": "test",
            "priority": Priority.LOW.value,
        }

        entity = Entity.from_dict(entity_dict)

        assert entity.entity_type == EntityType.VEHICLE


class TestEntityStatus:
    """Tests for Entity status handling."""

    def test_entity_initial_status_is_unknown(self):
        """Test that new entities have UNKNOWN status (constitutional default)."""
        entity = Entity(id=uuid4(), entity_type=EntityType.UNIT, status=EntityStatus.UNKNOWN)

        assert entity.status == EntityStatus.UNKNOWN

    def test_entity_status_from_string(self):
        """Test creating entity from dict with string status."""
        entity_dict = {
            "id": uuid4(),
            "entity_type": EntityType.ALERT,
            "status": "active",
            "data": {},
            "source": "test",
            "priority": Priority.CRITICAL.value,
        }

        entity = Entity.from_dict(entity_dict)

        assert entity.status == EntityStatus.ACTIVE

    def test_entity_status_values(self):
        """Test that all status values are accessible."""
        for status in EntityStatus:
            assert isinstance(status.value, str)
            assert len(status.value) > 0


class TestEntityPriority:
    """Tests for Entity priority handling."""

    def test_entity_default_priority_is_medium(self):
        """Test that entities have MEDIUM priority by default in EntityData."""
        entity = Entity(id=uuid4(), entity_type=EntityType.UNIT, status=EntityStatus.UNKNOWN)

        assert entity.priority == Priority.MEDIUM

    def test_entity_priority_from_string(self):
        """Test creating entity from dict with string priority."""
        entity_dict = {
            "id": uuid4(),
            "entity_type": EntityType.TASK,
            "status": EntityStatus.UNKNOWN,
            "data": {},
            "source": "test",
            "priority": "high",
        }

        entity = Entity.from_dict(entity_dict)

        assert entity.priority == Priority.HIGH


class TestEntitySerialization:
    """Tests for Entity serialization."""

    def test_entity_to_dict(self):
        """Test entity serialization to dictionary."""
        entity = Entity(
            id=uuid4(),
            entity_type=EntityType.UNIT,
            status=EntityStatus.UNKNOWN,
            source="test-source",
            priority=Priority.HIGH,
        )

        entity_dict = entity.to_dict()

        assert isinstance(entity_dict, dict)
        assert "id" in entity_dict
        assert "entity_type" in entity_dict
        assert entity_dict["entity_type"] == "unit"
        assert "status" in entity_dict
        assert "priority" in entity_dict

    def test_entity_to_dict_contains_data(self):
        """Test that to_dict includes entity data."""
        data = EntityData(callsign="BRAVO-1")
        entity = Entity(id=uuid4(), entity_type=EntityType.CONTACT, status=EntityStatus.UNKNOWN, data=data)

        entity_dict = entity.to_dict()

        assert "data" in entity_dict
        assert entity_dict["data"]["callsign"] == "BRAVO-1"

    def test_entity_from_dict_round_trip(self):
        """Test that entity can be serialized and deserialized."""
        original = Entity(
            id=uuid4(),
            entity_type=EntityType.VEHICLE,
            status=EntityStatus.UNKNOWN,
            source="round-trip-test",
            priority=Priority.HIGH,
        )

        entity_dict = original.to_dict()
        restored = Entity.from_dict(entity_dict)

        assert restored.id == original.id
        assert restored.entity_type == original.entity_type
        assert restored.source == original.source
        assert restored.priority == original.priority


class TestEntityData:
    """Tests for EntityData model."""

    def test_entity_data_empty_creation(self):
        """Test EntityData creation with no fields."""
        data = EntityData()

        assert data.callsign is None
        assert data.name is None
        assert data.description is None
        assert data.latitude is None
        assert data.longitude is None
        assert data.altitude is None
        assert data.status_text is None
        assert data.custom_fields == {}
        assert data.tags == set()

    def test_entity_data_creation_with_fields(self):
        """Test EntityData creation with fields."""
        data = EntityData(
            callsign="CHARLIE-1",
            name="Charlie Team",
            description="Charlie operational unit",
            latitude=38.8977,
            longitude=-77.0365,
            altitude=10.0,
            status_text="On mission",
            custom_fields={"team_size": 5},
            tags={"blue", "ground"},
        )

        assert data.callsign == "CHARLIE-1"
        assert data.name == "Charlie Team"
        assert data.latitude == 38.8977
        assert data.longitude == -77.0365
        assert data.custom_fields == {"team_size": 5}
        assert data.tags == {"blue", "ground"}

    def test_entity_data_to_dict(self):
        """Test EntityData serialization."""
        data = EntityData(callsign="DELTA-1", tags={"red", "air"})

        data_dict = data.to_dict()

        assert isinstance(data_dict, dict)
        assert data_dict["callsign"] == "DELTA-1"
        assert data_dict["tags"] == ["red", "air"]
        assert "custom_fields" in data_dict

    def test_entity_data_from_dict(self):
        """Test EntityData deserialization."""
        data_dict = {
            "callsign": "ECHO-1",
            "name": "Echo Team",
            "tags": ["alpha", "beta"],
        }

        data = EntityData.from_dict(data_dict)

        assert data.callsign == "ECHO-1"
        assert data.name == "Echo Team"
        assert data.tags == {"alpha", "beta"}

    def test_entity_data_round_trip(self):
        """Test EntityData serialization round-trip."""
        original = EntityData(callsign="FOXTROT-1", custom_fields={"special": True})

        data_dict = original.to_dict()
        restored = EntityData.from_dict(data_dict)

        assert restored.callsign == original.callsign
        assert restored.custom_fields == original.custom_fields


class TestEntityUpdate:
    """Tests for Entity update methods."""

    def test_mark_updated_changes_timestamp(self):
        """Test that mark_updated changes the updated_at timestamp."""
        entity = Entity(id=uuid4(), entity_type=EntityType.UNIT, status=EntityStatus.UNKNOWN)
        original_updated = entity.updated_at

        entity.mark_updated()

        assert entity.updated_at >= original_updated

    def test_mark_inactive_sets_status(self):
        """Test that mark_inactive sets status to INACTIVE."""
        entity = Entity(id=uuid4(), entity_type=EntityType.UNIT, status=EntityStatus.UNKNOWN)

        entity.mark_inactive()

        assert entity.status == EntityStatus.INACTIVE

class TestEntityDisplayName:
    """Tests for Entity display properties."""

    def test_display_name_callsign(self):
        """Test display_name returns callsign when set."""
        entity = Entity(
            id=uuid4(),
            entity_type=EntityType.UNIT,
            status=EntityStatus.UNKNOWN,
            data=EntityData(callsign="ALPHA-1"),
        )

        assert entity.display_name == "ALPHA-1"

    def test_display_name_name(self):
        """Test display_name returns name when callsign not set."""
        entity = Entity(
            id=uuid4(),
            entity_type=EntityType.UNIT,
            status=EntityStatus.UNKNOWN,
            data=EntityData(name="Alpha Squad"),
        )

        assert entity.display_name == "Alpha Squad"

    def test_display_name_fallback(self):
        """Test display_name falls back to type:id when no name/callsign."""
        entity = Entity(id=uuid4(), entity_type=EntityType.UNIT, status=EntityStatus.UNKNOWN)

        display = entity.display_name
        assert "unit" in display
        assert ":" in display


class TestEntityLocation:
    """Tests for Entity location properties."""

    def test_has_location_true(self):
        """Test has_location returns True when lat/lon are set."""
        entity = Entity(
            id=uuid4(),
            entity_type=EntityType.LOCATION,
            status=EntityStatus.UNKNOWN,
            data=EntityData(latitude=38.8977, longitude=-77.0365),
        )

        assert entity.has_location is True

    def test_has_location_false_no_coords(self):
        """Test has_location returns False when coords not set."""
        entity = Entity(id=uuid4(), entity_type=EntityType.LOCATION, status=EntityStatus.UNKNOWN)

        assert entity.has_location is False

    def test_location_tuple(self):
        """Test location_tuple returns (lat, lon) tuple."""
        entity = Entity(
            id=uuid4(),
            entity_type=EntityType.LOCATION,
            status=EntityStatus.UNKNOWN,
            data=EntityData(latitude=38.8977, longitude=-77.0365),
        )

        assert entity.location_tuple == (38.8977, -77.0365)

    def test_location_tuple_none(self):
        """Test location_tuple returns None when no location."""
        entity = Entity(id=uuid4(), entity_type=EntityType.LOCATION, status=EntityStatus.UNKNOWN)

        assert entity.location_tuple is None


class TestEntityTags:
    """Tests for Entity tag methods."""

    def test_add_tag(self):
        """Test adding a tag to entity."""
        entity = Entity(id=uuid4(), entity_type=EntityType.UNIT, status=EntityStatus.UNKNOWN)

        entity.add_tag("blue")

        assert "blue" in entity.data.tags

    def test_remove_tag(self):
        """Test removing a tag from entity."""
        entity = Entity(id=uuid4(), entity_type=EntityType.UNIT, status=EntityStatus.UNKNOWN)
        entity.add_tag("red")

        entity.remove_tag("red")

        assert "red" not in entity.data.tags


# =============================================================================
# INVALID DATA TESTS
# =============================================================================

class TestEntityInvalidData:
    """Tests for Entity handling of invalid data."""

    def test_entity_type_must_be_valid_enum(self):
        """Test that invalid entity type raises error."""
        with pytest.raises(ValueError):
            Entity.from_dict({
                "id": uuid4(),
                "entity_type": "invalid_type",
                "status": "active",
                "data": {},
                "source": "test",
                "priority": "medium",
            })

    def test_entity_status_must_be_valid_enum(self):
        """Test that invalid status raises error."""
        with pytest.raises(ValueError):
            Entity.from_dict({
                "id": uuid4(),
                "entity_type": "unit",
                "status": "invalid_status",
                "data": {},
                "source": "test",
                "priority": "medium",
            })

    def test_entity_priority_must_be_valid_enum(self):
        """Test that invalid priority raises error."""
        with pytest.raises(ValueError):
            Entity.from_dict({
                "id": uuid4(),
                "entity_type": "unit",
                "status": "active",
                "data": {},
                "source": "test",
                "priority": "invalid_priority",
            })


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
