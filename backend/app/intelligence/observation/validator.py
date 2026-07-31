"""Observation Validator.

Validates observations according to ENTITY-001 Constitutional rules.
Validation is deterministic and comprehensive.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from pydantic import ValidationError

from app.intelligence.observation.types import (
    ObservationType,
    SourceType,
    ProcessingStatus,
)
from app.intelligence.observation.schema import (
    ObservationCreate,
    ProvenanceData,
    ObservationReject,
)


class ObservationValidationError(Exception):
    """Base validation error with detailed error information."""

    def __init__(self, message: str, field: Optional[str] = None, code: Optional[str] = None):
        self.message = message
        self.field = field
        self.code = code or "VALIDATION_ERROR"
        super().__init__(self.message)


class DuplicateObservationError(ObservationValidationError):
    """Raised when a duplicate immutable_id is detected."""

    def __init__(self, immutable_id: str):
        self.immutable_id = immutable_id
        super().__init__(
            message=f"Duplicate observation: {immutable_id}",
            field="immutable_id",
            code="DUPLICATE_OBSERVATION",
        )


class InvalidTimestampError(ObservationValidationError):
    """Raised when timestamp is invalid or in the future."""

    def __init__(self, timestamp: Any):
        super().__init__(
            message=f"Invalid timestamp: {timestamp}",
            field="timestamp",
            code="INVALID_TIMESTAMP",
        )


class UnsupportedObservationTypeError(ObservationValidationError):
    """Raised when observation_type is not recognized."""

    def __init__(self, observation_type: str):
        super().__init__(
            message=f"Unsupported observation type: {observation_type}",
            field="observation_type",
            code="UNSUPPORTED_OBSERVATION_TYPE",
        )


class ObservationValidator:
    """Validates observations against constitutional requirements.

    This validator implements deterministic validation rules derived
    from ENTITY-001. It is a pure function - no side effects.

    Validation Rules:
    1. Reject malformed observations (schema validation)
    2. Reject missing mandatory fields
    3. Reject duplicate immutable IDs
    4. Reject invalid timestamps
    5. Reject unsupported observation types

    Thread Safety:
    This class is stateless and thread-safe. All validation
    methods are pure functions.
    """

    # Maximum allowed timestamp drift into the future (5 minutes)
    MAX_FUTURE_DRIFT_SECONDS = 300

    # Valid observation types
    VALID_OBSERVATION_TYPES: set = {
        "radio", "signal", "atak", "rest_api", "operator",
        "speech", "camera", "sensor", "other"
    }

    # Valid source types
    VALID_SOURCE_TYPES: set = {
        "driver", "plugin", "api", "operator", "ai", "system"
    }

    def __init__(self, duplicate_checker: Optional[callable] = None):
        """Initialize validator with optional duplicate checker.

        Args:
            duplicate_checker: Optional callback to check for duplicate
                               immutable_ids. Function signature:
                               (immutable_id: str) -> bool
        """
        self._duplicate_checker = duplicate_checker

    def validate(self, data: Dict[str, Any]) -> Tuple[bool, Optional[List[str]], Optional[ObservationCreate]]:
        """Validate observation data.

        This is the main entry point for validation. It performs
        all validation checks in a deterministic manner.

        Args:
            data: Raw observation data dictionary.

        Returns:
            Tuple of (is_valid, errors, validated_observation)
            - is_valid: True if validation passed
            - errors: List of error messages if validation failed
            - validated_observation: Validated ObservationCreate if valid, None otherwise
        """
        errors: List[str] = []

        # 1. Schema validation using Pydantic
        try:
            observation = ObservationCreate.model_validate(data)
        except ValidationError as e:
            for error in e.errors():
                field_path = ".".join(str(loc) for loc in error.get("loc", []))
                msg = error.get("msg", "Validation error")
                errors.append(f"Schema validation failed: {field_path} - {msg}")
            return False, errors, None

        # 2. Check for duplicate immutable_id
        if observation.immutable_id and self._duplicate_checker:
            try:
                if self._duplicate_checker(observation.immutable_id):
                    errors.append(f"Duplicate observation ID: {observation.immutable_id}")
                    return False, errors, None
            except Exception as e:
                errors.append(f"Duplicate check failed: {str(e)}")
                return False, errors, None

        # 3. Validate timestamp (if present in provenance)
        if observation.provenance.original_timestamp:
            timestamp_errors = self._validate_timestamp(observation.provenance.original_timestamp)
            if timestamp_errors:
                errors.extend(timestamp_errors)

        # 4. Validate observation type
        if observation.observation_type not in self.VALID_OBSERVATION_TYPES:
            errors.append(
                f"Unsupported observation type: {observation.observation_type}. "
                f"Valid types: {', '.join(sorted(self.VALID_OBSERVATION_TYPES))}"
            )

        # 5. Validate source type
        if observation.source_type not in self.VALID_SOURCE_TYPES:
            errors.append(
                f"Unsupported source type: {observation.source_type}. "
                f"Valid types: {', '.join(sorted(self.VALID_SOURCE_TYPES))}"
            )

        # 6. Validate evidence payload is not empty
        if not observation.evidence_payload:
            errors.append("Evidence payload cannot be empty")

        if errors:
            return False, errors, None

        return True, None, observation

    def _validate_timestamp(self, timestamp: datetime) -> List[str]:
        """Validate timestamp is not in the future beyond allowed drift.

        Args:
            timestamp: Timestamp to validate.

        Returns:
            List of error messages if validation fails.
        """
        errors: List[str] = []

        if not isinstance(timestamp, datetime):
            errors.append(f"Invalid timestamp type: {type(timestamp).__name__}")
            return errors

        # Ensure timezone-aware
        if timestamp.tzinfo is None:
            errors.append("Timestamp must be timezone-aware (UTC)")
            return errors

        # Check if too far in the future
        now = datetime.now(timezone.utc)
        max_future = now.timestamp() + self.MAX_FUTURE_DRIFT_SECONDS

        if timestamp.timestamp() > max_future:
            errors.append(
                f"Timestamp is too far in the future: {timestamp.isoformat()}. "
                f"Maximum allowed drift: {self.MAX_FUTURE_DRIFT_SECONDS} seconds"
            )

        return errors

    def validate_immutable_id(self, immutable_id: str) -> Tuple[bool, Optional[str]]:
        """Validate an immutable ID for uniqueness.

        Args:
            immutable_id: The ID to check.

        Returns:
            Tuple of (is_unique, error_message)
        """
        if not immutable_id:
            return False, "immutable_id cannot be empty"

        if len(immutable_id) > 255:
            return False, "immutable_id exceeds maximum length of 255 characters"

        if self._duplicate_checker and self._duplicate_checker(immutable_id):
            return False, f"Duplicate observation ID: {immutable_id}"

        return True, None

    @staticmethod
    def create_rejection_response(
        errors: List[str],
        original_data: Optional[Dict[str, Any]] = None,
        error_code: str = "VALIDATION_FAILED"
    ) -> ObservationReject:
        """Create a standardized rejection response.

        Args:
            errors: List of validation error messages.
            original_data: Optional original data for debugging.
            error_code: Error code for programmatic handling.

        Returns:
            ObservationReject instance.
        """
        return ObservationReject(
            error_code=error_code,
            error_message="Observation validation failed",
            rejected_data=original_data,
            validation_errors=errors,
        )


def validate_observation_schema(data: Dict[str, Any]) -> Tuple[bool, Optional[List[str]], Optional[ObservationCreate]]:
    """Standalone validation function for simple use cases.

    This function provides a convenient way to validate observations
    without instantiating the validator class.

    Args:
        data: Raw observation data dictionary.

    Returns:
        Tuple of (is_valid, errors, validated_observation)
    """
    validator = ObservationValidator()
    return validator.validate(data)
