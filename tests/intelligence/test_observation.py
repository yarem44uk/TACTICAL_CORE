"""WO-007-001 Regression Tests.

These tests verify the WO-007-001 fixes:
- CF1: SQLAlchemy metadata collision (metadata -> observation_metadata)
- CF2: ValidationError shadowing (ValidationError -> ObservationValidationError)

These tests use the ACTUAL implemented API from:
backend/app/intelligence/observation/

NOT hypothetical APIs.
NOT nonexistent imports.
NOT nonexistent fields.

Author: Tactical Core Engineering Team
Version: 1.0
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import pytest
from pydantic import ValidationError as PydanticValidationError

# Import ACTUAL exports from observation module
from app.intelligence.observation import (
    # Schema
    ProvenanceData,
    ObservationCreate,
    ObservationResponse,
    ObservationList,
    ObservationReject,
    # Validator
    ObservationValidator,
    ObservationValidationError,
    DuplicateObservationError,
    InvalidTimestampError,
    UnsupportedObservationTypeError,
    validate_observation_schema,
    # Model
    Observation,
)


# =============================================================================
# CF1 REGRESSION TESTS - SQLAlchemy Metadata Collision
# =============================================================================

class TestCF1MetadataCollision:
    """Tests for CF1: metadata -> observation_metadata rename.

    These tests verify that:
    1. Observation imports successfully
    2. SQLAlchemy mapping initializes without 'metadata' attribute conflict
    3. The ORM uses 'observation_metadata' not 'metadata'
    4. No 'metadata' ORM attribute exists (would cause SQLAlchemy collision)
    """

    def test_observation_imports_successfully(self):
        """CF1: Observation model imports without attribute conflict."""
        # This test verifies that the import works at all
        # If there was a 'metadata' attribute conflict, import would fail
        assert Observation is not None
        assert hasattr(Observation, 'id')

    def test_observation_has_observation_metadata_not_metadata(self):
        """CF1: ORM uses observation_metadata, not metadata.

        The fix renamed 'metadata' to 'observation_metadata' to avoid
        SQLAlchemy Declarative Base.metadata collision.
        """
        # observation_metadata should exist
        assert hasattr(Observation, 'observation_metadata'),             "ORM must have 'observation_metadata' attribute"

        # 'metadata' should NOT exist as an ORM column/mapped_column
        # We check this by verifying observation_metadata is a proper ORM column
        # by looking at the class __dict__ (not inherited attributes)
        orm_columns = [attr for attr in Observation.__mapper__.columns 
                      if attr.key]
        column_names = [col.name for col in orm_columns]

        assert 'observation_metadata' in column_names,             "'observation_metadata' must be an ORM column"

        # Verify 'metadata' is NOT a mapped column
        # (would indicate collision was not fixed)
        assert 'metadata' not in column_names,             "'metadata' must NOT be an ORM column (CF1 collision not fixed)"

    def test_observation_can_be_instantiated(self):
        """CF1: Observation can be created using actual constructor.

        Uses REAL fields: source, evidence_payload, observation_metadata, etc.
        """
        # Create valid observation data using actual API fields
        observation_data = {
            'source': 'test_driver',
            'source_type': 'driver',
            'evidence_payload': {'raw_data': 'test evidence'},
            'observation_type': 'radio',
            'provenance': ProvenanceData().model_dump(),
            'source_confidence': 0.75,
            'tags': ['test', 'cf1'],
            'observation_metadata': {'test_key': 'test_value'},  # Actual field
        }

        # Create ObservationCreate to validate
        obs_create = ObservationCreate.model_validate(observation_data)

        # Create Observation model instance
        obs = Observation.from_observation_create(obs_create)

        # Verify the fields exist
        assert obs.source == 'test_driver'
        assert obs.evidence_payload == {'raw_data': 'test evidence'}
        assert obs.observation_metadata == {'test_key': 'test_value'}

        # Verify metadata attribute does not exist on this instance
        assert not hasattr(obs, 'metadata') or obs.metadata is None,             "Observation must not have 'metadata' attribute"

    def test_observation_create_uses_real_schema(self):
        """CF1: ObservationCreate uses real schema with correct fields.

        Verifies that:
        - 'evidence_payload' is a required field (not 'observation_data')
        - 'source' is used (not 'source_id')
        """
        # Valid data using ACTUAL fields
        valid_data = {
            'source': 'api_source',
            'source_type': 'api',
            'evidence_payload': {'message': 'test'},
            'observation_type': 'signal',
            'provenance': ProvenanceData(
                driver_id='driver_001',
                observation_metadata={'api_version': '1.0'}
            ).model_dump(),
        }

        obs_create = ObservationCreate.model_validate(valid_data)

        # Verify correct field names
        assert obs_create.source == 'api_source'
        assert obs_create.evidence_payload == {'message': 'test'}
        assert obs_create.provenance.observation_metadata == {'api_version': '1.0'}


# =============================================================================
# CF2 REGRESSION TESTS - ValidationError Shadowing
# =============================================================================

class TestCF2ValidationErrorShadowing:
    """Tests for CF2: ValidationError -> ObservationValidationError rename.

    These tests verify that:
    1. ObservationValidationError exists and is distinct
    2. pydantic.ValidationError is not shadowed
    3. Validation handles malformed input gracefully
    4. No NameError from shadowing
    """

    def test_observation_validation_error_exists(self):
        """CF2: Custom exception is renamed to avoid shadowing."""
        assert ObservationValidationError is not None
        assert issubclass(ObservationValidationError, Exception)

    def test_validation_error_does_not_shadow_pydantic(self):
        """CF2: pydantic.ValidationError is accessible (not shadowed).

        The fix renamed the custom exception so pydantic's ValidationError
        is not shadowed in the validator module namespace.
        """
        # Import pydantic ValidationError directly
        from pydantic import ValidationError as PydanticError

        # Verify it's accessible
        assert PydanticError is not None

        # Verify our custom exception is different
        assert ObservationValidationError is not PydanticError
        assert not issubclass(ObservationValidationError, PydanticError)

    def test_validator_handles_none_input(self):
        """CF2: Validator handles None input gracefully."""
        validator = ObservationValidator()

        # None input should fail validation, not raise NameError
        is_valid, errors, result = validator.validate(None)

        assert is_valid is False
        assert errors is not None
        assert len(errors) > 0

    def test_validator_handles_list_input(self):
        """CF2: Validator handles list input gracefully."""
        validator = ObservationValidator()

        # List input should fail validation
        is_valid, errors, result = validator.validate(["not", "a", "dict"])

        assert is_valid is False
        assert errors is not None

    def test_validator_handles_missing_required_fields(self):
        """CF2: Validator handles missing required fields."""
        validator = ObservationValidator()

        # Missing required 'source' field
        incomplete_data = {
            'source_type': 'driver',
            'evidence_payload': {'data': 'test'},
            'observation_type': 'radio',
            'provenance': ProvenanceData().model_dump(),
        }

        is_valid, errors, result = validator.validate(incomplete_data)

        assert is_valid is False
        assert errors is not None
        assert len(errors) > 0
        # Check for source field error
        source_errors = [e for e in errors if 'source' in e.lower()]
        assert len(source_errors) > 0

    def test_validator_handles_incorrect_field_type(self):
        """CF2: Validator handles incorrect field types."""
        validator = ObservationValidator()

        # source_confidence should be float, not string
        invalid_type_data = {
            'source': 'test',
            'source_type': 'driver',
            'evidence_payload': {'data': 'test'},
            'observation_type': 'radio',
            'provenance': ProvenanceData().model_dump(),
            'source_confidence': 'high',  # Should be float 0.0-1.0
        }

        is_valid, errors, result = validator.validate(invalid_type_data)

        assert is_valid is False
        assert errors is not None

    def test_validator_handles_garbage_dict(self):
        """CF2: Validator handles garbage input gracefully."""
        validator = ObservationValidator()

        # Completely invalid data
        garbage = {
            'foo': 'bar',
            'baz': 123,
            'nested': {'deep': 'value'},
        }

        is_valid, errors, result = validator.validate(garbage)

        assert is_valid is False
        assert errors is not None
        assert len(errors) > 0

    def test_observation_validation_error_is_raised_correctly(self):
        """CF2: Custom exception is raised with correct attributes."""
        error = ObservationValidationError(
            message="Test error",
            field="test_field",
            code="TEST_ERROR"
        )

        assert error.message == "Test error"
        assert error.field == "test_field"
        assert error.code == "TEST_ERROR"
        assert str(error) == "Test error"

    def test_duplicate_observation_error(self):
        """CF2: DuplicateObservationError has correct structure."""
        error = DuplicateObservationError("test-id-123")

        assert error.immutable_id == "test-id-123"
        assert error.code == "DUPLICATE_OBSERVATION"
        assert "test-id-123" in str(error)

    def test_invalid_timestamp_error(self):
        """CF2: InvalidTimestampError has correct structure."""
        error = InvalidTimestampError("invalid")

        assert error.code == "INVALID_TIMESTAMP"
        assert "timestamp" in str(error).lower()

    def test_unsupported_observation_type_error(self):
        """CF2: UnsupportedObservationTypeError has correct structure."""
        error = UnsupportedObservationTypeError("invalid_type")

        assert error.code == "UNSUPPORTED_OBSERVATION_TYPE"
        assert "invalid_type" in str(error)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestObservationIntegration:
    """Integration tests using real schemas and validators."""

    def test_validate_observation_schema_function(self):
        """Test standalone validate_observation_schema function."""
        valid_data = {
            'source': 'integration_test',
            'source_type': 'test',
            'evidence_payload': {'test': True},
            'observation_type': 'test',
            'provenance': ProvenanceData().model_dump(),
        }

        is_valid, errors, result = validate_observation_schema(valid_data)

        assert is_valid is True
        assert errors is None
        assert result is not None
        assert isinstance(result, ObservationCreate)

    def test_observation_create_with_all_fields(self):
        """Test creating observation with all available fields."""
        data = {
            'source': 'full_test',
            'source_type': 'driver',
            'evidence_payload': {
                'audio': 'base64_encoded_audio',
                'transcription': 'test transcription'
            },
            'observation_type': 'speech',
            'immutable_id': 'test-immutable-001',
            'provenance': ProvenanceData(
                driver_id='driver_abc',
                device_id='device_xyz',
                original_timestamp=datetime.now(timezone.utc),
                observation_metadata={'language': 'uk'}
            ).model_dump(),
            'source_confidence': 0.95,
            'tags': ['speech', 'transcription', 'verified'],
        }

        obs_create = ObservationCreate.model_validate(data)

        assert obs_create.source == 'full_test'
        assert obs_create.source_confidence == 0.95
        assert 'speech' in obs_create.tags
        assert obs_create.provenance.observation_metadata == {'language': 'uk'}

    def test_provenance_data_uses_observation_metadata(self):
        """Test that ProvenanceData uses observation_metadata field."""
        provenance = ProvenanceData(
            driver_id='driver_1',
            observation_metadata={'key1': 'value1', 'key2': 'value2'}
        )

        # Verify the field exists and works
        assert provenance.observation_metadata == {'key1': 'value1', 'key2': 'value2'}

        # Verify frozen (immutable)
        assert provenance.model_config.get('frozen', False) is True


# =============================================================================
# SCHEMA VALIDATION TESTS
# =============================================================================

class TestSchemaValidation:
    """Tests for Pydantic schema validation."""

    def test_observation_reject_schema(self):
        """Test ObservationReject schema creation."""
        reject = ObservationReject(
            error_code='TEST_ERROR',
            error_message='Test rejection message',
            rejected_data={'test': 'data'},
            validation_errors=['Error 1', 'Error 2']
        )

        assert reject.error_code == 'TEST_ERROR'
        assert len(reject.validation_errors) == 2
        assert reject.frozen is True

    def test_provenance_data_is_frozen(self):
        """Test that ProvenanceData is immutable."""
        provenance = ProvenanceData(driver_id='test')

        # Should be frozen
        with pytest.raises(Exception):  # Pydantic raises ValidationError
            provenance.driver_id = 'changed'

    def test_observation_list_schema(self):
        """Test ObservationList schema."""
        obs_list = ObservationList(
            items=[],
            total=0,
            page=1,
            page_size=10
        )

        assert obs_list.total == 0
        assert obs_list.page == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
