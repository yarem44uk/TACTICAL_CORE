"""
Observation Validation Framework.

This module provides comprehensive validation for all Observations
entering the Event Pipeline. Validates against:
1. Schema structure
2. Required fields
3. UUID format
4. Timestamp validity
5. Source registration
6. Observation integrity
7. Constitutional compliance

Author: Tactical Core Engineering Team
Version: 1.0
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4
import hashlib
import re


class ValidationStatus(Enum):
    """Validation result status."""
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class ValidationCategory(Enum):
    """Categories of validation checks."""
    SCHEMA = "schema"
    CONSTITUTIONAL = "constitutional"
    SOURCE = "source"
    TIMESTAMP = "timestamp"
    INTEGRITY = "integrity"
    FIELD = "field"


@dataclass
class ValidationIssue:
    """Represents a single validation issue."""
    category: ValidationCategory
    status: ValidationStatus
    message: str
    field: Optional[str] = None
    code: Optional[str] = None
    severity: str = "error"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "category": self.category.value,
            "status": self.status.value,
            "message": self.message,
            "field": self.field,
            "code": self.code,
            "severity": self.severity,
        }


@dataclass
class ValidationResult:
    """Complete validation result for an Observation."""
    status: ValidationStatus
    observation_id: Optional[str]
    timestamp: datetime
    issues: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    errors: List[ValidationIssue] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no FAIL issues)."""
        return self.status != ValidationStatus.FAIL

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0 or self.status == ValidationStatus.WARNING

    def add_issue(self, issue: ValidationIssue) -> None:
        """Add a validation issue and categorize it."""
        self.issues.append(issue)
        if issue.status == ValidationStatus.FAIL:
            self.errors.append(issue)
        elif issue.status == ValidationStatus.WARNING:
            self.warnings.append(issue)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "status": self.status.value,
            "observation_id": self.observation_id,
            "timestamp": self.timestamp.isoformat(),
            "is_valid": self.is_valid,
            "has_warnings": self.has_warnings,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [i.to_dict() for i in self.errors],
            "warnings": [i.to_dict() for i in self.warnings],
            "metadata": self.metadata,
        }


class SchemaValidator:
    """Validates Observation schema structure."""

    REQUIRED_FIELDS: Set[str] = {
        "source",
        "observation_type",
        "evidence_payload",
    }

    OPTIONAL_FIELDS: Set[str] = {
        "source_type",
        "provenance",
        "source_confidence",
        "tags",
        "immutable_id",
        "observation_metadata",
        "correlation_id",
    }

    ALL_FIELDS: Set[str] = REQUIRED_FIELDS | OPTIONAL_FIELDS

    UUID_PATTERN = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )

    @classmethod
    def validate_required_fields(
        cls,
        data: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Validate all required fields are present."""
        issues = []

        for field_name in cls.REQUIRED_FIELDS:
            if field_name not in data:
                issues.append(ValidationIssue(
                    category=ValidationCategory.FIELD,
                    status=ValidationStatus.FAIL,
                    message=f"Required field missing: {field_name}",
                    field=field_name,
                    code="MISSING_REQUIRED_FIELD",
                ))
            elif data[field_name] is None:
                issues.append(ValidationIssue(
                    category=ValidationCategory.FIELD,
                    status=ValidationStatus.FAIL,
                    message=f"Required field cannot be null: {field_name}",
                    field=field_name,
                    code="NULL_REQUIRED_FIELD",
                ))
            elif isinstance(data[field_name], str) and not data[field_name].strip():
                issues.append(ValidationIssue(
                    category=ValidationCategory.FIELD,
                    status=ValidationStatus.FAIL,
                    message=f"Required field cannot be empty: {field_name}",
                    field=field_name,
                    code="EMPTY_REQUIRED_FIELD",
                ))

        return issues

    @classmethod
    def validate_field_types(
        cls,
        data: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Validate field types are correct."""
        issues = []

        # source must be string
        if "source" in data and not isinstance(data["source"], str):
            issues.append(ValidationIssue(
                category=ValidationCategory.SCHEMA,
                status=ValidationStatus.FAIL,
                message="Field 'source' must be a string",
                field="source",
                code="INVALID_FIELD_TYPE",
            ))

        # observation_type must be string
        if "observation_type" in data and not isinstance(data["observation_type"], str):
            issues.append(ValidationIssue(
                category=ValidationCategory.SCHEMA,
                status=ValidationStatus.FAIL,
                message="Field 'observation_type' must be a string",
                field="observation_type",
                code="INVALID_FIELD_TYPE",
            ))

        # evidence_payload must be dict
        if "evidence_payload" in data and not isinstance(data["evidence_payload"], dict):
            issues.append(ValidationIssue(
                category=ValidationCategory.SCHEMA,
                status=ValidationStatus.FAIL,
                message="Field 'evidence_payload' must be a dictionary",
                field="evidence_payload",
                code="INVALID_FIELD_TYPE",
            ))

        # source_confidence must be float between 0 and 1
        if "source_confidence" in data and data["source_confidence"] is not None:
            conf = data["source_confidence"]
            if not isinstance(conf, (int, float)):
                issues.append(ValidationIssue(
                    category=ValidationCategory.SCHEMA,
                    status=ValidationStatus.FAIL,
                    message="Field 'source_confidence' must be a number",
                    field="source_confidence",
                    code="INVALID_FIELD_TYPE",
                ))
            elif conf < 0.0 or conf > 1.0:
                issues.append(ValidationIssue(
                    category=ValidationCategory.SCHEMA,
                    status=ValidationStatus.FAIL,
                    message="Field 'source_confidence' must be between 0.0 and 1.0",
                    field="source_confidence",
                    code="INVALID_CONFIDENCE_RANGE",
                ))

        # tags must be list
        if "tags" in data and data["tags"] is not None:
            if not isinstance(data["tags"], list):
                issues.append(ValidationIssue(
                    category=ValidationCategory.SCHEMA,
                    status=ValidationStatus.FAIL,
                    message="Field 'tags' must be a list",
                    field="tags",
                    code="INVALID_FIELD_TYPE",
                ))

        return issues

    @classmethod
    def validate_immutable_id(
        cls,
        data: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Validate immutable_id format if present."""
        issues = []

        if "immutable_id" in data and data["immutable_id"] is not None:
            imm_id = str(data["immutable_id"])
            if not cls.UUID_PATTERN.match(imm_id):
                issues.append(ValidationIssue(
                    category=ValidationCategory.INTEGRITY,
                    status=ValidationStatus.FAIL,
                    message="Field 'immutable_id' must be a valid UUID format",
                    field="immutable_id",
                    code="INVALID_UUID_FORMAT",
                ))

        return issues

    @classmethod
    def validate(
        cls,
        data: Dict[str, Any]
    ) -> Tuple[bool, List[ValidationIssue]]:
        """Run all schema validations."""
        all_issues = []
        all_issues.extend(cls.validate_required_fields(data))
        all_issues.extend(cls.validate_field_types(data))
        all_issues.extend(cls.validate_immutable_id(data))

        has_failures = any(i.status == ValidationStatus.FAIL for i in all_issues)
        return not has_failures, all_issues


class TimestampValidator:
    """Validates Observation timestamps."""

    MAX_FUTURE_DRIFT = timedelta(seconds=300)  # 5 minutes
    MAX_PAST_DRIFT = timedelta(days=365)  # 1 year

    @classmethod
    def validate_timestamp(
        cls,
        data: Dict[str, Any],
        created_at: Optional[datetime] = None
    ) -> List[ValidationIssue]:
        """Validate timestamp is valid and within acceptable range."""
        issues = []
        now = datetime.now(timezone.utc)

        # If no timestamp in data, check created_at
        timestamp = data.get("timestamp") or created_at

        if timestamp is None:
            issues.append(ValidationIssue(
                category=ValidationCategory.TIMESTAMP,
                status=ValidationStatus.WARNING,
                message="No timestamp provided - will use current time",
                field="timestamp",
                code="MISSING_TIMESTAMP",
            ))
            return issues

        # Parse timestamp
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                issues.append(ValidationIssue(
                    category=ValidationCategory.TIMESTAMP,
                    status=ValidationStatus.FAIL,
                    message=f"Invalid timestamp format: {timestamp}",
                    field="timestamp",
                    code="INVALID_TIMESTAMP_FORMAT",
                ))
                return issues

        if not timestamp.tzinfo:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        # Check if in future
        if timestamp > now + cls.MAX_FUTURE_DRIFT:
            issues.append(ValidationIssue(
                category=ValidationCategory.TIMESTAMP,
                status=ValidationStatus.FAIL,
                message="Timestamp is too far in the future",
                field="timestamp",
                code="FUTURE_TIMESTAMP",
            ))

        # Check if too far in past
        if timestamp < now - cls.MAX_PAST_DRIFT:
            issues.append(ValidationIssue(
                category=ValidationCategory.TIMESTAMP,
                status=ValidationStatus.WARNING,
                message="Timestamp is very old",
                field="timestamp",
                code="OLD_TIMESTAMP",
            ))

        return issues


class SourceValidator:
    """Validates Observation source registration."""

    VALID_SOURCE_TYPES: Set[str] = {
        "driver",
        "plugin",
        "api",
        "operator",
        "ai",
        "system",
    }

    VALID_OBSERVATION_TYPES: Set[str] = {
        "radio",
        "signal",
        "atak",
        "rest_api",
        "operator",
        "speech",
        "camera",
        "sensor",
        "other",
    }

    @classmethod
    def validate_source(
        cls,
        data: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Validate source and source_type."""
        issues = []

        source = data.get("source", "")
        source_type = data.get("source_type", "")

        # Check for empty source
        if not source or not source.strip():
            issues.append(ValidationIssue(
                category=ValidationCategory.SOURCE,
                status=ValidationStatus.FAIL,
                message="Source cannot be empty",
                field="source",
                code="EMPTY_SOURCE",
            ))
            return issues

        # Check source format (alphanumeric, underscores, hyphens)
        if not re.match(r'^[a-zA-Z0-9_-]+$', source):
            issues.append(ValidationIssue(
                category=ValidationCategory.SOURCE,
                status=ValidationStatus.FAIL,
                message="Source contains invalid characters (use alphanumeric, underscore, hyphen)",
                field="source",
                code="INVALID_SOURCE_FORMAT",
            ))

        # Validate source_type if present
        if source_type:
            if source_type not in cls.VALID_SOURCE_TYPES:
                issues.append(ValidationIssue(
                    category=ValidationCategory.SOURCE,
                    status=ValidationStatus.WARNING,
                    message=f"Unknown source_type: {source_type}",
                    field="source_type",
                    code="UNKNOWN_SOURCE_TYPE",
                ))

        return issues

    @classmethod
    def validate_observation_type(
        cls,
        data: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Validate observation_type."""
        issues = []

        obs_type = data.get("observation_type", "")

        if not obs_type:
            issues.append(ValidationIssue(
                category=ValidationCategory.SOURCE,
                status=ValidationStatus.FAIL,
                message="observation_type cannot be empty",
                field="observation_type",
                code="EMPTY_OBSERVATION_TYPE",
            ))
            return issues

        if obs_type not in cls.VALID_OBSERVATION_TYPES:
            issues.append(ValidationIssue(
                category=ValidationCategory.SOURCE,
                status=ValidationStatus.WARNING,
                message=f"Unknown observation_type: {obs_type}",
                field="observation_type",
                code="UNKNOWN_OBSERVATION_TYPE",
            ))

        return issues


class IntegrityValidator:
    """Validates Observation data integrity."""

    @classmethod
    def validate_evidence_payload(
        cls,
        data: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Validate evidence payload structure."""
        issues = []

        evidence = data.get("evidence_payload", {})

        if not evidence:
            issues.append(ValidationIssue(
                category=ValidationCategory.INTEGRITY,
                status=ValidationStatus.WARNING,
                message="evidence_payload is empty",
                field="evidence_payload",
                code="EMPTY_EVIDENCE",
            ))

        # Check for common patterns that should exist
        # (but don't fail - just warn)
        return issues

    @classmethod
    def compute_integrity_hash(
        cls,
        data: Dict[str, Any]
    ) -> str:
        """Compute integrity hash for the observation."""
        # Create a deterministic string representation
        key_fields = {
            "source": data.get("source", ""),
            "observation_type": data.get("observation_type", ""),
            "evidence_payload": data.get("evidence_payload", {}),
            "timestamp": str(data.get("timestamp", "")),
        }

        content = str(sorted(key_fields.items()))
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class ConstitutionalValidator:
    """Validates against ENTITY-001 Constitutional rules."""

    @classmethod
    def validate_constitutional_rules(
        cls,
        data: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Validate constitutional requirements from ENTITY-001.

        Article 7: Observations are immutable
        - Once created, observations cannot be modified
        - This validator ensures immutability metadata is present

        Article 8: Knowledge evolves, observations never change
        - Each observation must have unique immutable_id
        """
        issues = []

        # Check for immutable_id (Article 8)
        if not data.get("immutable_id"):
            issues.append(ValidationIssue(
                category=ValidationCategory.CONSTITUTIONAL,
                status=ValidationStatus.WARNING,
                message="Observation missing immutable_id - one will be generated",
                field="immutable_id",
                code="MISSING_IMMUTABLE_ID",
            ))

        # Check confidence is within constitutional bounds
        confidence = data.get("source_confidence", 0.5)
        if confidence is not None:
            if confidence < 0.0 or confidence > 1.0:
                issues.append(ValidationIssue(
                    category=ValidationCategory.CONSTITUTIONAL,
                    status=ValidationStatus.FAIL,
                    message="Confidence must be between 0.0 and 1.0 (ENTITY-001 Article 7)",
                    field="source_confidence",
                    code="INVALID_CONFIDENCE",
                ))

        return issues


class ObservationValidationFramework:
    """
    Complete Observation Validation Framework.

    Validates all Observations before they enter the Event Pipeline.
    Returns comprehensive ValidationResult with PASS/WARNING/FAIL status.
    """

    def __init__(
        self,
        duplicate_checker: Optional[callable] = None,
        allow_unknown_source_types: bool = True,
        allow_unknown_observation_types: bool = True,
    ):
        """Initialize the validation framework."""
        self._duplicate_checker = duplicate_checker or (lambda x: False)
        self.allow_unknown_source_types = allow_unknown_source_types
        self.allow_unknown_observation_types = allow_unknown_observation_types

    def validate(
        self,
        data: Dict[str, Any],
        observation_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> ValidationResult:
        """
        Perform complete validation of observation data.

        Args:
            data: Observation data dictionary
            observation_id: Optional observation ID
            created_at: Optional creation timestamp

        Returns:
            ValidationResult with status and issues
        """
        result = ValidationResult(
            status=ValidationStatus.PASS,
            observation_id=observation_id,
            timestamp=datetime.now(timezone.utc),
        )

        # Run all validations
        all_issues = []

        # 1. Schema validation
        schema_valid, schema_issues = SchemaValidator.validate(data)
        all_issues.extend(schema_issues)

        # 2. Timestamp validation
        timestamp_issues = TimestampValidator.validate_timestamp(data, created_at)
        all_issues.extend(timestamp_issues)

        # 3. Source validation
        source_issues = SourceValidator.validate_source(data)
        all_issues.extend(source_issues)

        # 4. Observation type validation
        obs_type_issues = SourceValidator.validate_observation_type(data)
        all_issues.extend(obs_type_issues)

        # 5. Integrity validation
        integrity_issues = IntegrityValidator.validate_evidence_payload(data)
        all_issues.extend(integrity_issues)

        # 6. Constitutional validation
        const_issues = ConstitutionalValidator.validate_constitutional_rules(data)
        all_issues.extend(const_issues)

        # 7. Duplicate check
        immutable_id = data.get("immutable_id")
        if immutable_id and self._duplicate_checker(immutable_id):
            all_issues.append(ValidationIssue(
                category=ValidationCategory.INTEGRITY,
                status=ValidationStatus.FAIL,
                message="Duplicate observation (immutable_id already exists)",
                field="immutable_id",
                code="DUPLICATE_OBSERVATION",
            ))

        # Add all issues to result
        for issue in all_issues:
            result.add_issue(issue)

        # Determine overall status
        has_failures = len(result.errors) > 0
        has_warnings = len(result.warnings) > 0

        if has_failures:
            result.status = ValidationStatus.FAIL
        elif has_warnings:
            result.status = ValidationStatus.WARNING
        else:
            result.status = ValidationStatus.PASS

        # Add metadata
        result.metadata = {
            "schema_valid": schema_valid,
            "validation_categories_run": [
                c.value for c in ValidationCategory
            ],
            "total_issues": len(all_issues),
        }

        return result

    def validate_fast(
        self,
        data: Dict[str, Any]
    ) -> ValidationStatus:
        """
        Fast validation returning only status.

        Use for quick checks where details are not needed.
        """
        result = self.validate(data)
        return result.status


# Convenience function
def validate_observation(
    data: Dict[str, Any],
    observation_id: Optional[str] = None,
) -> ValidationResult:
    """
    Validate a single observation.

    Args:
        data: Observation data dictionary
        observation_id: Optional observation ID

    Returns:
        ValidationResult
    """
    framework = ObservationValidationFramework()
    return framework.validate(data, observation_id)
