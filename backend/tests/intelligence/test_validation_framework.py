"""
Unit Tests for WO-007-003: Observation Validation Framework.

Comprehensive tests covering:
- Schema validation
- Timestamp validation
- Source validation
- Integrity validation
- Constitutional validation
- ValidationResult object
- Fast validation

Author: Tactical Core Engineering Team
Version: 1.0
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from app.intelligence.observation.validation_framework import (
    ValidationStatus,
    ValidationCategory,
    ValidationIssue,
    ValidationResult,
    SchemaValidator,
    TimestampValidator,
    SourceValidator,
    IntegrityValidator,
    ConstitutionalValidator,
    ObservationValidationFramework,
    validate_observation,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def valid_observation_data():
    """Valid observation data for testing."""
    return {
        "source": "multicast_driver",
        "source_type": "driver",
        "observation_type": "radio",
        "evidence_payload": {"transcription": "Test message"},
        "source_confidence": 0.85,
        "tags": ["radio", "test"],
        "immutable_id": str(uuid4()),
    }


@pytest.fixture
def validation_framework():
    """Create validation framework instance."""
    return ObservationValidationFramework()


# =============================================================================
# TESTS: ValidationStatus
# =============================================================================

class TestValidationStatus:
    """Tests for ValidationStatus enum."""

    def test_status_values(self):
        """Test enum values."""
        assert ValidationStatus.PASS.value == "pass"
        assert ValidationStatus.WARNING.value == "warning"
        assert ValidationStatus.FAIL.value == "fail"

    def test_status_comparison(self):
        """Test status comparisons."""
        assert ValidationStatus.PASS != ValidationStatus.FAIL
        assert ValidationStatus.WARNING != ValidationStatus.PASS


# =============================================================================
# TESTS: ValidationIssue
# =============================================================================

class TestValidationIssue:
    """Tests for ValidationIssue."""

    def test_creation_fail(self):
        """Test creating a FAIL issue."""
        issue = ValidationIssue(
            category=ValidationCategory.SCHEMA,
            status=ValidationStatus.FAIL,
            message="Test failure",
            field="test_field",
            code="TEST_ERROR",
        )

        assert issue.status == ValidationStatus.FAIL
        assert issue.category == ValidationCategory.SCHEMA
        assert issue.message == "Test failure"
        assert issue.field == "test_field"
        assert issue.code == "TEST_ERROR"

    def test_creation_warning(self):
        """Test creating a WARNING issue."""
        issue = ValidationIssue(
            category=ValidationCategory.SOURCE,
            status=ValidationStatus.WARNING,
            message="Test warning",
            severity="warn",
        )

        assert issue.status == ValidationStatus.WARNING
        assert issue.severity == "warn"

    def test_to_dict(self):
        """Test converting issue to dictionary."""
        issue = ValidationIssue(
            category=ValidationCategory.TIMESTAMP,
            status=ValidationStatus.FAIL,
            message="Invalid timestamp",
            field="timestamp",
            code="INVALID_TS",
        )

        data = issue.to_dict()
        assert data["status"] == "fail"
        assert data["category"] == "timestamp"
        assert data["message"] == "Invalid timestamp"
        assert data["field"] == "timestamp"


# =============================================================================
# TESTS: ValidationResult
# =============================================================================

class TestValidationResult:
    """Tests for ValidationResult."""

    def test_creation_pass(self):
        """Test creating a PASS result."""
        result = ValidationResult(
            status=ValidationStatus.PASS,
            observation_id="test-123",
            timestamp=datetime.now(timezone.utc),
        )

        assert result.is_valid is True
        assert result.has_warnings is False
        assert len(result.errors) == 0

    def test_creation_with_issues(self):
        """Test creating result with issues."""
        result = ValidationResult(
            status=ValidationStatus.FAIL,
            observation_id="test-123",
            timestamp=datetime.now(timezone.utc),
        )

        # Add a FAIL issue
        result.add_issue(ValidationIssue(
            category=ValidationCategory.SCHEMA,
            status=ValidationStatus.FAIL,
            message="Schema error",
            code="SCHEMA_ERR",
        ))

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert len(result.issues) == 1

    def test_add_issue_categorization(self):
        """Test that issues are properly categorized."""
        result = ValidationResult(
            status=ValidationStatus.PASS,
            observation_id="test-123",
            timestamp=datetime.now(timezone.utc),
        )

        # Add FAIL issue
        result.add_issue(ValidationIssue(
            category=ValidationCategory.SOURCE,
            status=ValidationStatus.FAIL,
            message="Fail issue",
        ))

        # Add WARNING issue
        result.add_issue(ValidationIssue(
            category=ValidationCategory.TIMESTAMP,
            status=ValidationStatus.WARNING,
            message="Warning issue",
        ))

        assert len(result.errors) == 1
        assert len(result.warnings) == 1
        assert result.status == ValidationStatus.FAIL

    def test_is_valid_property(self):
        """Test is_valid property."""
        # PASS
        result = ValidationResult(
            status=ValidationStatus.PASS,
            observation_id="test",
            timestamp=datetime.now(timezone.utc),
        )
        assert result.is_valid is True

        # WARNING (still valid)
        result = ValidationResult(
            status=ValidationStatus.WARNING,
            observation_id="test",
            timestamp=datetime.now(timezone.utc),
        )
        assert result.is_valid is True

        # FAIL (not valid)
        result = ValidationResult(
            status=ValidationStatus.FAIL,
            observation_id="test",
            timestamp=datetime.now(timezone.utc),
        )
        assert result.is_valid is False

    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = ValidationResult(
            status=ValidationStatus.PASS,
            observation_id="test-123",
            timestamp=datetime.now(timezone.utc),
        )

        data = result.to_dict()
        assert data["status"] == "pass"
        assert data["observation_id"] == "test-123"
        assert data["is_valid"] is True
        assert data["error_count"] == 0


# =============================================================================
# TESTS: SchemaValidator
# =============================================================================

class TestSchemaValidator:
    """Tests for SchemaValidator."""

    def test_validate_required_fields_success(self, valid_observation_data):
        """Test required fields validation passes."""
        issues = SchemaValidator.validate_required_fields(valid_observation_data)
        assert len(issues) == 0

    def test_validate_required_fields_missing(self):
        """Test missing required fields detected."""
        data = {"source": "test"}
        issues = SchemaValidator.validate_required_fields(data)

        assert len(issues) >= 2  # observation_type and evidence_payload missing
        assert any(i.code == "MISSING_REQUIRED_FIELD" for i in issues)

    def test_validate_required_fields_empty(self):
        """Test empty required fields detected."""
        data = {
            "source": "test",
            "observation_type": "",
            "evidence_payload": {},
        }
        issues = SchemaValidator.validate_required_fields(data)

        assert any(i.code == "EMPTY_REQUIRED_FIELD" for i in issues)

    def test_validate_field_types(self):
        """Test field type validation."""
        # Invalid source type
        data = {
            "source": 123,  # Should be string
            "observation_type": "radio",
            "evidence_payload": {},
        }
        issues = SchemaValidator.validate_field_types(data)
        assert len(issues) > 0
        assert any("source" in i.message.lower() for i in issues)

    def test_validate_field_types_confidence(self):
        """Test confidence range validation."""
        # Out of range
        data = {
            "source": "test",
            "observation_type": "radio",
            "evidence_payload": {},
            "source_confidence": 1.5,  # Invalid
        }
        issues = SchemaValidator.validate_field_types(data)
        assert any(i.code == "INVALID_CONFIDENCE_RANGE" for i in issues)

    def test_validate_immutable_id_valid(self, valid_observation_data):
        """Test valid UUID format."""
        issues = SchemaValidator.validate_immutable_id(valid_observation_data)
        assert len(issues) == 0

    def test_validate_immutable_id_invalid(self):
        """Test invalid UUID format detected."""
        data = {"immutable_id": "not-a-uuid"}
        issues = SchemaValidator.validate_immutable_id(data)
        assert any(i.code == "INVALID_UUID_FORMAT" for i in issues)

    def test_validate_complete_success(self, valid_observation_data):
        """Test complete validation passes."""
        valid, issues = SchemaValidator.validate(valid_observation_data)
        assert valid is True
        assert len(issues) == 0

    def test_validate_complete_failure(self):
        """Test complete validation catches failures."""
        data = {}  # Missing everything
        valid, issues = SchemaValidator.validate(data)
        assert valid is False
        assert len(issues) > 0


# =============================================================================
# TESTS: TimestampValidator
# =============================================================================

class TestTimestampValidator:
    """Tests for TimestampValidator."""

    def test_validate_valid_timestamp(self):
        """Test valid timestamp passes."""
        now = datetime.now(timezone.utc)
        data = {"timestamp": now.isoformat()}
        issues = TimestampValidator.validate_timestamp(data)
        assert len(issues) == 0

    def test_validate_missing_timestamp_warning(self):
        """Test missing timestamp generates warning."""
        data = {}
        issues = TimestampValidator.validate_timestamp(data)
        assert any(i.code == "MISSING_TIMESTAMP" for i in issues)

    def test_validate_invalid_format(self):
        """Test invalid timestamp format detected."""
        data = {"timestamp": "not-a-date"}
        issues = TimestampValidator.validate_timestamp(data)
        assert any(i.code == "INVALID_TIMESTAMP_FORMAT" for i in issues)

    def test_validate_future_timestamp(self):
        """Test future timestamp detected."""
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        data = {"timestamp": future.isoformat()}
        issues = TimestampValidator.validate_timestamp(data)
        assert any(i.code == "FUTURE_TIMESTAMP" for i in issues)

    def test_validate_old_timestamp_warning(self):
        """Test very old timestamp generates warning."""
        old = datetime.now(timezone.utc) - timedelta(days=400)
        data = {"timestamp": old.isoformat()}
        issues = TimestampValidator.validate_timestamp(data)
        assert any(i.code == "OLD_TIMESTAMP" for i in issues)


# =============================================================================
# TESTS: SourceValidator
# =============================================================================

class TestSourceValidator:
    """Tests for SourceValidator."""

    def test_validate_source_valid(self, valid_observation_data):
        """Test valid source passes."""
        issues = SourceValidator.validate_source(valid_observation_data)
        assert len(issues) == 0

    def test_validate_source_empty(self):
        """Test empty source detected."""
        data = {"source": ""}
        issues = SourceValidator.validate_source(data)
        assert any(i.code == "EMPTY_SOURCE" for i in issues)

    def test_validate_source_invalid_chars(self):
        """Test invalid characters detected."""
        data = {"source": "invalid source name!"}
        issues = SourceValidator.validate_source(data)
        assert any(i.code == "INVALID_SOURCE_FORMAT" for i in issues)

    def test_validate_observation_type_valid(self):
        """Test valid observation type passes."""
        data = {"observation_type": "radio"}
        issues = SourceValidator.validate_observation_type(data)
        assert len(issues) == 0

    def test_validate_observation_type_empty(self):
        """Test empty observation type detected."""
        data = {"observation_type": ""}
        issues = SourceValidator.validate_observation_type(data)
        assert any(i.code == "EMPTY_OBSERVATION_TYPE" for i in issues)

    def test_validate_observation_type_unknown(self):
        """Test unknown observation type generates warning."""
        data = {"observation_type": "unknown_type"}
        issues = SourceValidator.validate_observation_type(data)
        assert any(i.code == "UNKNOWN_OBSERVATION_TYPE" for i in issues)


# =============================================================================
# TESTS: IntegrityValidator
# =============================================================================

class TestIntegrityValidator:
    """Tests for IntegrityValidator."""

    def test_validate_empty_evidence_warning(self):
        """Test empty evidence generates warning."""
        data = {"evidence_payload": {}}
        issues = IntegrityValidator.validate_evidence_payload(data)
        assert any(i.code == "EMPTY_EVIDENCE" for i in issues)

    def test_compute_integrity_hash(self):
        """Test integrity hash computation."""
        data = {
            "source": "test",
            "observation_type": "radio",
            "evidence_payload": {"test": "value"},
        }
        hash1 = IntegrityValidator.compute_integrity_hash(data)

        # Same data should produce same hash
        hash2 = IntegrityValidator.compute_integrity_hash(data)
        assert hash1 == hash2

        # Different data should produce different hash
        data2 = {**data, "source": "other"}
        hash3 = IntegrityValidator.compute_integrity_hash(data2)
        assert hash1 != hash3


# =============================================================================
# TESTS: ConstitutionalValidator
# =============================================================================

class TestConstitutionalValidator:
    """Tests for ConstitutionalValidator."""

    def test_validate_missing_immutable_id_warning(self):
        """Test missing immutable_id generates warning."""
        data = {}
        issues = ConstitutionalValidator.validate_constitutional_rules(data)
        assert any(i.code == "MISSING_IMMUTABLE_ID" for i in issues)

    def test_validate_invalid_confidence_fail(self):
        """Test invalid confidence fails constitutional check."""
        data = {"source_confidence": 1.5}
        issues = ConstitutionalValidator.validate_constitutional_rules(data)
        assert any(i.code == "INVALID_CONFIDENCE" for i in issues)


# =============================================================================
# TESTS: ObservationValidationFramework
# =============================================================================

class TestObservationValidationFramework:
    """Tests for ObservationValidationFramework."""

    def test_validate_valid_observation(self, validation_framework, valid_observation_data):
        """Test validation of valid observation passes."""
        result = validation_framework.validate(valid_observation_data)

        assert result.status == ValidationStatus.PASS
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_invalid_schema(self, validation_framework):
        """Test validation catches schema errors."""
        data = {}  # Missing everything
        result = validation_framework.validate(data)

        assert result.status == ValidationStatus.FAIL
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_validate_duplicate_detection(self, validation_framework, valid_observation_data):
        """Test duplicate detection."""
        # Create duplicate checker that always returns True
        framework = ObservationValidationFramework(
            duplicate_checker=lambda x: True
        )
        result = framework.validate(valid_observation_data)

        assert result.status == ValidationStatus.FAIL
        assert any(i.code == "DUPLICATE_OBSERVATION" for i in result.errors)

    def test_validate_fast(self, validation_framework, valid_observation_data):
        """Test fast validation."""
        status = validation_framework.validate_fast(valid_observation_data)
        assert status == ValidationStatus.PASS

    def test_validate_fast_invalid(self, validation_framework):
        """Test fast validation with invalid data."""
        status = validation_framework.validate_fast({})
        assert status == ValidationStatus.FAIL


# =============================================================================
# TESTS: Convenience Function
# =============================================================================

class TestValidateObservation:
    """Tests for validate_observation convenience function."""

    def test_validate_observation_valid(self, valid_observation_data):
        """Test convenience function with valid data."""
        result = validate_observation(valid_observation_data)
        assert result.is_valid is True

    def test_validate_observation_invalid(self):
        """Test convenience function with invalid data."""
        result = validate_observation({})
        assert result.is_valid is False

    def test_validate_observation_with_id(self, valid_observation_data):
        """Test convenience function with observation ID."""
        obs_id = "test-obs-123"
        result = validate_observation(valid_observation_data, obs_id)
        assert result.observation_id == obs_id


# =============================================================================
# TESTS: Integration Scenarios
# =============================================================================

class TestValidationIntegration:
    """Integration tests for validation framework."""

    def test_complete_valid_observation(self, validation_framework):
        """Test complete validation of a valid observation."""
        data = {
            "source": "multicast_driver",
            "source_type": "driver",
            "observation_type": "radio",
            "evidence_payload": {"transcription": "Alpha checking in"},
            "source_confidence": 0.95,
            "tags": ["radio", "alpha"],
            "immutable_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        result = validation_framework.validate(data)

        assert result.status == ValidationStatus.PASS
        assert result.is_valid is True
        assert result.has_warnings is False

    def test_complete_invalid_observation(self, validation_framework):
        """Test complete validation of an invalid observation."""
        data = {
            "source": "",  # Invalid
            "observation_type": "radio",
            "evidence_payload": {},  # Empty
            "source_confidence": 2.0,  # Invalid
        }

        result = validation_framework.validate(data)

        assert result.status == ValidationStatus.FAIL
        assert result.is_valid is False
        assert len(result.errors) >= 3  # Multiple errors

    def test_observation_with_warnings(self, validation_framework):
        """Test observation with warnings but no failures."""
        data = {
            "source": "custom_driver",
            "source_type": "unknown_type",  # Unknown
            "observation_type": "radio",
            "evidence_payload": {},  # Empty
            "immutable_id": str(uuid4()),
        }

        result = validation_framework.validate(data)

        # Should have warnings but not failures
        assert result.status == ValidationStatus.WARNING
        assert result.is_valid is True
        assert len(result.warnings) > 0
        assert len(result.errors) == 0
